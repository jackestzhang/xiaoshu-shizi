"""把插画里的一个角色抠成透明贴纸，并补一张没有他的背景。

    python pipeline/cutout.py --lesson L03 --page 1 --name farmer \
        --box 320,320,1060,930 --shift 480

产出：
    app/assets/actors/<lesson>_<name>.webp   透明贴纸（RGBA）
    app/assets/art/<lesson>_p<page>_bg.webp  去掉该角色的背景（同名尺寸）
并打印贴纸在原图中的百分比位置，供 data/lessons/*.json 的 actor 字段使用。

背景修补没有用 cv2.inpaint：Telea 在大面积土地上会糊成一片，还会把远山的
绿色拖进田里。这里改成「同一水平线从右侧搬一块过来」——田垄是横向的，
横移后纹理接得上；再按羽化后的 mask 混合，边界不会出现硬边。
搬移距离必须大于角色自身的宽度，否则会把角色自己的像素复制回来。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from rembg import new_session, remove

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

ART = common.APP / "assets" / "art"
ACTORS = common.APP / "assets" / "actors"
DISPLAY_W = 1280          # 与 art.py 输出的展示尺寸保持一致


def cut(src: Image.Image, box: tuple[int, int, int, int], model: str):
    crop = src.crop(box)
    sess = new_session(model)
    rgba = remove(crop, session=sess)
    a = np.array(rgba)[:, :, 3]
    ys, xs = np.where(a > 24)
    if not len(xs):
        common.die("没抠出任何东西，检查 --box")
    pad = 3
    l = max(0, xs.min() - pad)
    t = max(0, ys.min() - pad)
    r = min(rgba.width, xs.max() + 1 + pad)
    b = min(rgba.height, ys.max() + 1 + pad)
    sticker = rgba.crop((l, t, r, b))

    # 收一圈边：rembg 的软边里混着背景色，直接用会在米色纸上留一圈脏边
    arr = np.array(sticker).astype(np.float32)
    alpha = arr[:, :, 3] / 255.0
    alpha = np.clip((alpha - 0.12) / 0.88, 0, 1)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.6)
    arr[:, :, 3] = alpha * 255
    sticker = Image.fromarray(arr.astype(np.uint8))

    return sticker, (box[0] + l, box[1] + t, box[0] + r, box[1] + b)


def fill_bg(src_bgr: np.ndarray, mask: np.ndarray, shift: int, soft_top: float) -> np.ndarray:
    """用低分辨率扩散把洞补成一片「虚掉的背景」。

    这块洞有 460×460，左边三步是一棵大树、右边也是一棵大树：整块横移会把
    树搬到他帽子上，左右镜像会镜像出两根树干。角色只是原地小幅动，露出来
    的永远只是轮廓边上一窄条，所以这里要的不是「一模一样的纹理」，而是
    「颜色和明暗接得上、没有具体物件」。把洞缩到 1/8、用周围像素往洞里扩散
    到收敛、再放大回来，得到的就是一层跟环境同色的柔光背景——边缘处完全
    连续，露出来也只是一片虚化的远山和田。
    """
    h, w = mask.shape
    scale = 8
    small = cv2.resize(src_bgr, (max(1, w // scale), max(1, h // scale)), interpolation=cv2.INTER_AREA)
    m_small = cv2.resize(mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    img = small.copy()
    img[m_small] = np.median(small.reshape(-1, 3), axis=0)
    for _ in range(320):                      # 低分辨率上扩散到收敛
        blur = cv2.blur(img, (5, 5))
        img[m_small] = blur[m_small]
    soft = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)

    a = (cv2.GaussianBlur(mask, (0, 0), 2.5) / 255.0)[:, :, None]
    out = src_bgr * (1 - a) + soft * a
    return np.clip(out, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1（原图像素）")
    ap.add_argument("--shift", type=int, default=0, help="保留参数，镜像填充不需要")
    ap.add_argument("--model", default="isnet-general-use")
    ap.add_argument("--soft-top", type=float, default=0.0, help="这一高度以上的填洞结果做柔化（0=不柔化）")
    args = ap.parse_args()

    src_path = common.ROOT / "art" / args.lesson / f"p{args.page}.png"
    if not src_path.exists():
        common.die(f"找不到 {src_path}")
    src = Image.open(src_path).convert("RGB")
    box = tuple(int(v) for v in args.box.split(","))

    sticker, sbox = cut(src, box, args.model)
    ACTORS.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)

    # 贴纸按展示分辨率等比缩小，避免 base64 里塞进 3 倍多余像素
    scale = DISPLAY_W / src.width
    out_w = max(1, round(sticker.width * scale))
    out_h = max(1, round(sticker.height * scale))
    sticker.resize((out_w, out_h), Image.LANCZOS).save(
        ACTORS / f"{args.lesson}_{args.name}.webp", "WEBP", quality=92, method=6)

    # 背景：用贴纸的 alpha 反过来当遮罩，位置对得上
    alpha_full = np.zeros((src.height, src.width), np.uint8)
    sticker_alpha = np.array(sticker)[:, :, 3]
    alpha_full[sbox[1]:sbox[3], sbox[0]:sbox[2]] = sticker_alpha
    mask = (alpha_full > 24).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    solid = np.zeros_like(mask)
    cv2.drawContours(solid, cnts, -1, 255, -1)
    mask = cv2.dilate(solid, np.ones((5, 5), np.uint8))

    bg = fill_bg(cv2.imread(str(src_path)).astype(np.float32), mask, args.shift, args.soft_top)
    bg_img = Image.fromarray(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB))
    # 与 art.py 完全一致：1536×1024 裁成 5:3、纵向 0.46 处对齐后缩到 1280×768。
    # 百分比框必须按裁完的这张算，否则贴纸会整体偏下。
    bg_img = ImageOps.fit(bg_img, (DISPLAY_W, 768), Image.LANCZOS, centering=(0.5, 0.46))
    bg_img.save(ART / f"{args.lesson}_p{args.page}_bg.webp", "WEBP", quality=92, method=6)

    # 给 data/lessons 用的百分比框（左/上/宽/高，相对**展示图**）
    frame_h = src.width * 768 / DISPLAY_W
    top = (src.height - frame_h) * 0.46
    pct = lambda v, total: round(v / total * 100, 2)
    info = {
        "actor": f"assets/actors/{args.lesson}_{args.name}.webp",
        "x": pct((sbox[0] + sbox[2]) / 2, src.width),
        "y": pct((sbox[1] + sbox[3]) / 2 - top, frame_h),
        "w": pct(sbox[2] - sbox[0], src.width),
        "h": pct(sbox[3] - sbox[1], frame_h),
        "art": f"assets/art/{args.lesson}_p{args.page}_bg.webp",
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
