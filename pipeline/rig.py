"""把农夫的上半身再拆一层：躯干（含头）与「肩—臂—锄」分开。

腰已是一级关节（绕腰点俯仰）。要在它之上再加一级肩关节，就得让手臂能
单独绕肩转。原画里手臂挡住了身后的上衣，直接挖会露出一个透明的洞，
所以挖完必须把洞补成布。

    python pipeline/rig.py --preview /tmp/rig-preview.png --angle 9

产出：
    app/assets/actors/L03_farmer_torso.webp   腰以上、不含臂
    app/assets/actors/L03_farmer_arm.webp     肩以下的手臂 + 手 + 锄头
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ACTORS = common.APP / "assets" / "actors"
SRC = "L03_farmer_up.webp"

# 肩关节绕的那个点。取自领口右下方、袖管转折处（原图 382×382 坐标）。
SHOULDER = (196, 106)
# 上身两层的画布比原图大一圈，给锄头摆动留地方。
PAD = 44
CANVAS = 382 + PAD * 2
# 洞只可能出现在袖管盖住的那块躯干上。上边界留在 116：再往上离枢轴太近，
# 臂的圆弧本来就一直盖着，补了反而会在领口边上留一块浅色。
HOLE_BOX = (150, 92, 240, 218)
# 补布时取样的一块纯衣料（躯干中段的蓝布，没有高光也没有褶）。
SAMPLE_BOX = (88, 128, 150, 186)

# 「肩—袖—手—锄」的外轮廓。顺时针一圈：先沿袖子上缘走到手腕，顺着
# 锄柄上缘到锄刃，再沿刃的外沿绕回来，最后顺着袖管内缘回到肩。
ARM_POLY = [
    # 肩端特意画成以肩为圆心的一小段弧（左端伸进躯干里 12px），
    # 这样臂无论转到哪个角度，枢轴附近始终盖着袖子的像素，接缝不会裂开。
    (184, 96), (180, 108), (184, 122),
    (196, 130), (206, 140), (219, 158), (231, 182), (240, 203), (247, 212),
    # 锄柄这一段上下各留 10~15px 余量。贴着柄边切很容易漏掉下缘那条深色
    # 阴影，臂一转，底图上就留下第二条柄，看起来像扛了两把锄头。
    (262, 214), (300, 231), (340, 262), (382, 284),
    (382, 382), (284, 382),
    (312, 338), (352, 328), (300, 284), (250, 256), (240, 244),
    (228, 218), (216, 200), (208, 180), (200, 150), (196, 120),
]


def load(name: str) -> np.ndarray:
    return np.array(Image.open(ACTORS / name).convert("RGBA")).astype(np.float32)


def arm_mask(shape) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.array(ARM_POLY, np.int32)], 255)
    # 膨胀一圈再和原图 alpha 取交，边界落在 rembg 那条软边上，
    # 不会留下 polygon 硬切出来的锯齿黑点。
    return cv2.dilate(m, np.ones((7, 7), np.uint8))


def hole_mask(arm_m: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = HOLE_BOX
    h = np.zeros(arm_m.shape, bool)
    h[y0:y1, x0:x1] = (arm_m[y0:y1, x0:x1] > 0) & (alpha[y0:y1, x0:x1] > 200)
    return h


def cut_mask(arm_m: np.ndarray) -> np.ndarray:
    """挖躯干用的范围。

    默认就用手臂自己那张掩膜（比轮廓胖 3px）。早先为了吃掉柄下缘那道
    半透明投影，多挖了十几像素，结果静止时袖子和躯干之间露出一条白缝——
    那圈余量没人盖。现在只把确知是「柄」的两块矩形单独抹掉。
    """
    m = arm_m.copy()
    # 手和柄在 x≥245 这条线右边，那里本来就没有躯干，整条挖干净最省事；
    # 不然臂一转开，底图上会留下半截幽灵柄。
    m[196:336, 222:340] = 255
    return (m > 0).astype(np.float32)


def patch(rgb: np.ndarray, alpha: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """把洞补成布。

    洞是一条最宽三十来像素的斜条，两端都是同一块蓝布。做法很朴素：从躯干
    中段抠一块干净衣料，拉伸成洞的形状盖上去，再羽化掉边界。试过泊松融合
    （seamlessClone），它会把补丁的笔触抹平，反而更像贴了一块塑料片——
    布纹本身就是这块区域最该保留的东西。
    """
    ys, xs = np.nonzero(hole)
    if not len(ys):
        return rgb
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1

    sx0, sy0, sx1, sy1 = SAMPLE_BOX
    sample = rgb[sy0:sy1, sx0:sx1]
    # 不要整块缩放：把样本直接拉伸，会把样本里那块领口高光一起拉进来，
    # 补出来是一大片浅色。只取它的高频笔触，铺在样本的平均色上。
    base = sample.reshape(-1, 3).mean(axis=0)
    hi = sample - base
    bh, bw = by1 - by0, bx1 - bx0
    th, tw = hi.shape[:2]
    reps = (bh // th + 2, bw // tw + 2, 1)
    piece = np.clip(base + np.tile(hi, reps)[:bh, :bw] * .9, 0, 255)

    out = rgb.copy()
    soft = cv2.GaussianBlur((hole * 255).astype(np.uint8), (0, 0), 1.6)
    m = (soft[by0:by1, bx0:bx1].astype(np.float32) / 255.0)[..., None]
    out[by0:by1, bx0:bx1] = rgb[by0:by1, bx0:bx1] * (1 - m) + piece * m
    return np.clip(out, 0, 255)


def on_canvas(img: np.ndarray) -> np.ndarray:
    out = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    out[PAD:PAD + img.shape[0], PAD:PAD + img.shape[1]] = img
    return out


def rotate_about(img: np.ndarray, pivot, deg: float) -> np.ndarray:
    """绕任意点旋转，按预乘 alpha 处理。

    不预乘的话，透明区的 RGB（抠图后是白或黑）会被插值进边缘，
    转完就是一圈毛茸茸的噪点。
    """
    h, w = img.shape[:2]
    a = img[:, :, 3:4] / 255.0
    pm = np.dstack([img[:, :, :3] * a, img[:, :, 3]])
    m = cv2.getRotationMatrix2D((pivot[0], pivot[1]), -deg, 1.0)
    return cv2.warpAffine(pm, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def unpremultiply(img: np.ndarray) -> np.ndarray:
    a = np.clip(img[:, :, 3:4] / 255.0, 0, 1)
    rgb = np.where(a > 0, img[:, :, :3] / np.maximum(a, 1e-6), 0)
    return np.dstack([np.clip(rgb, 0, 255), img[:, :, 3]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="")
    ap.add_argument("--angle", type=float, default=9.0, help="预览时把臂转多少度")
    args = ap.parse_args()

    up = load(SRC)
    alpha = up[:, :, 3]
    rgb = up[:, :, :3]

    arm_m = arm_mask(up.shape)
    arm_bin = (arm_m > 0).astype(np.float32)
    cut = cut_mask(arm_m)
    # 挖掉的范围内、原本是实心躯干的地方，都要补成布，否则露出来是一圈浅边。
    # 领口右下角本来就有指甲盖大一块透明（帽檐和脸之间的缝），臂一抬就成
    # 一个方方正正的洞；先把 alpha 的碎口闭合，再取交集，这块也一并补上。
    solid = cv2.morphologyEx((alpha > 200).astype(np.uint8) * 255,
                             cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8))
    hole = (cut > 0) & (solid > 0)
    keep = np.zeros_like(hole)
    x0, y0, x1, y1 = HOLE_BOX
    keep[y0:y1, x0:x1] = True
    hole &= keep

    torso_rgb = patch(rgb, alpha, hole)
    # 臂盖住的那块躯干要从底图上让开，否则臂一转，底下那条旧袖子就露出来
    # ——变成两条胳膊。让开的地方由上面补的布顶着。
    torso_a = (alpha / 255.0) * (1.0 - cut)
    torso_a[hole] = 1.0
    torso = np.dstack([torso_rgb, torso_a * 255]).astype(np.uint8)

    arm = np.dstack([rgb, (alpha / 255.0) * arm_bin * 255]).astype(np.uint8)

    # 画布四周留出 PAD：原图锄刃已经顶到右下角，臂一抬，刃就转到画布外，
    # 那一截在 PNG 里根本没有像素，渲染出来就是「刃被削掉一块」。
    torso = on_canvas(torso)
    arm = on_canvas(arm)

    Image.fromarray(torso).save(ACTORS / "L03_farmer_torso.webp", lossless=True)
    Image.fromarray(arm).save(ACTORS / "L03_farmer_arm.webp", lossless=True)
    print("写出 torso / arm", ACTORS, "洞 %.0f 像素" % hole.sum(),
          "画布 %d 边距 %d" % (CANVAS, PAD))

    if args.preview:
        angles = [0, -args.angle, args.angle]
        w = h = CANVAS
        sheet = Image.new("RGB", (w * (len(angles) + 1), h), (250, 245, 235))
        sheet.paste(Image.fromarray(torso), (0, 0), Image.fromarray(torso))
        slab = arm.astype(np.float32)
        for i, ang in enumerate(angles):
            cell = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            cell.alpha_composite(Image.fromarray(torso))
            rot = unpremultiply(rotate_about(slab, (SHOULDER[0] + PAD, SHOULDER[1] + PAD), ang)).astype(np.uint8)
            cell.alpha_composite(Image.fromarray(rot))
            sheet.paste(cell, (w * (i + 1), 0), cell)
        sheet.save(args.preview)
        print("预览", args.preview)


if __name__ == "__main__":
    main()
