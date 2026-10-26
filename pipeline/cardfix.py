"""给识字卡库里缺的字补卡：黑楷字 + 红古文字 + 彩色象形 + 拼音配词。

背景：用户提供的《象形识字卡大全》PDF 共 1400 张，覆盖 115 个字表字，
但雨、鸟、鱼、田、小、门这 6 个整字不在其中（库里有雷/雪、鸡/鸭、男/界这类
带相应偏旁的字，唯独没有这几个字本身）。用甲骨文兜底会和彩色卡风格割裂，
所以按原卡的版式补画。

用法：
    python3 pipeline/cardfix.py            # 合成
    python3 pipeline/cardfix.py --preview  # 只出一张总览图

版式取自原卡（app/assets/cards/shan.webp，640x736）：
    黑楷字   x 0.21-0.41  y 0.13-0.30
    红古字   x 0.57-0.81  y 0.15-0.31
    彩色图   中心 (0.50, 0.62)  最大 310px
    拼音/词  居中 y 0.86 / 0.91
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "app" / "assets" / "cards"
KAI_DIR = Path("/tmp/wenkai/package/files")
SLUG_KAI = "lxgwwenkai-regular-subset-*.woff2"


def kai_for(char: str) -> Path:
    """霞鹜文楷是 webfont 分片，每个分片只含一部分字，按码点找含该字的分片。"""
    from fontTools.ttLib import TTFont
    cp = ord(char)
    cache = kai_for.cache
    if cp in cache:
        return cache[cp]
    for f in sorted(KAI_DIR.glob(SLUG_KAI)):
        try:
            t = TTFont(f, lazy=True)
            cmap = t.getBestCmap()
            t.close()
        except Exception:
            continue
        if cp in cmap:
            cache[cp] = f
            return f
    raise SystemExit(f"楷体分片里找不到「{char}」（需要先下载 lxgw-wenkai-webfont）")


kai_for.cache = {}
LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CJK = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"

W, H = 640, 736
PAPER = (254, 254, 254)
INK = (30, 28, 26)
GREY = (110, 102, 92)

# 字 → (拼音, 配词, 彩图文件名关键词)
ITEMS = {
    "小": ("xiǎo", "小兔", "00-25-35"),
    "雨": ("yǔ", "下雨", "00-25-57"),
    "门": ("mén", "大门", "00-27-13"),
    "田": ("tián", "田地", "00-27-26"),
    "鸟": ("niǎo", "小鸟", "00-28-37"),
    "鱼": ("yú", "小鱼", "00-28-54"),
}

SLUG = {"小": "xiao", "雨": "yu", "门": "men", "田": "tian", "鸟": "niao", "鱼": "yu2"}


def trim(im: Image.Image, pad: int = 0) -> Image.Image:
    """按不透明/非白像素裁掉空白。"""
    a = np.asarray(im.convert("RGBA"))
    if im.mode == "RGBA":
        mask = a[:, :, 3] > 12
    else:
        rgb = a[:, :, :3].astype(int)
        mask = rgb.min(axis=2) < 235
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return im
    x0, x1 = max(0, xs.min()-pad), min(im.width, xs.max()+1+pad)
    y0, y1 = max(0, ys.min()-pad), min(im.height, ys.max()+1+pad)
    return im.crop((x0, y0, x1, y1))


def fit_into(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """等比缩放，塞进 box，保持比例。"""
    s = min(box_w / im.width, box_h / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def glyph(char: str, size: int = 190, fs: int = 130) -> Image.Image:
    """黑楷字：固定字号，只在画布内居中。

    原卡每个字的字号一致，笔画少的字（小）自然就小，
    按外框缩放会把「小」拉得和「田」一样大，反而失真。
    """
    font = ImageFont.truetype(str(kai_for(char)), fs)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), char, font=font)
    d.text(((size - (bb[2]-bb[0]))/2 - bb[0], (size - (bb[3]-bb[1]))/2 - bb[1]),
           char, font=font, fill=INK + (255,))
    return im


def find_color(char: str) -> Path:
    key = ITEMS[char][2]
    hits = [p for p in (ROOT / "art" / "cards-fix").glob("*.png") if key in p.name]
    if not hits:
        raise SystemExit(f"找不到「{char}」的彩图（关键词 {key}）")
    return hits[0]


# AI 图底色是 #FBF6EC，卡片是纯白；直接贴会看到一块方形色差。
# 按通道白平衡把底色拉到纯白，物体颜色只轻微偏移。
PAPER_AI = (251, 246, 236)


def whiten(im: Image.Image) -> Image.Image:
    """把 AI 图的米色底换成纯白。

    四角采样当底色（不同图的底色深浅不一），按色差替换，边缘做一次羽化，
    否则贴在白卡上会看到一个方形轮廓。
    """
    a = np.asarray(im).astype(np.float32)
    corners = np.stack([a[2, 2], a[2, -3], a[-3, 2], a[-3, -3]])
    bg = np.median(corners, axis=0)
    dist = np.abs(a - bg).max(axis=2)
    a[dist < 14] = 255
    # 过渡带：把 14-26 的色差按比例推向白色
    band = (dist >= 14) & (dist < 26)
    k = ((dist - 14) / 12.0)[..., None]
    a[band] = 255 - (255 - a[band]) * k[band]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def color_pic(char: str) -> Image.Image:
    im = Image.open(find_color(char)).convert("RGB")
    # 裁掉四周 6%（含右下角水印）
    bx = int(im.width * 0.06)
    im = im.crop((bx, bx, im.width - bx, im.height - bx))
    im = whiten(im)
    return trim(im, pad=4)


def compose(char: str) -> Image.Image:
    pinyin, word, _ = ITEMS[char]
    canvas = Image.new("RGB", (W, H), PAPER)

    # 黑楷字：左上
    g = glyph(char)
    canvas.paste(g, (102, 66), g)

    # 红古字：右上，按统一画布缩放（字形本身已在 100x100 内归一化）
    red = Image.open(f"/tmp/red/{SLUG[char]}.png").convert("RGBA")
    red = red.resize((190, 190), Image.LANCZOS)
    canvas.paste(red, (346, 66), red)

    # 彩色象形：中下
    pic = fit_into(color_pic(char), 292, 292)
    canvas.paste(pic, ((W - pic.width)//2, 330 + (292 - pic.height)//2))

    # 拼音 + 配词
    d = ImageDraw.Draw(canvas)
    try:
        # 外层大字卡也会显示拼音和配词，卡内这份要小一点，避免重复得太抢眼
        f1 = ImageFont.truetype(LATIN, 26)
        f2 = ImageFont.truetype(CJK, 24) if Path(CJK).exists() else f1
    except Exception:
        f1 = f2 = ImageFont.load_default()
    tw = d.textlength(pinyin, font=f1)
    d.text(((W - tw)/2, 632), pinyin, font=f1, fill=GREY)
    tw = d.textlength(word, font=f2)
    d.text(((W - tw)/2, 668), word, font=f2, fill=INK)
    return canvas


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    made = []
    for char in ITEMS:
        im = compose(char)
        p = CARDS / f"{SLUG[char]}.webp"
        im.save(p, "WEBP", quality=88, method=6)
        made.append((char, p))
        print(f"  ✓ {char} → {p.relative_to(ROOT)} ({p.stat().st_size//1024} KB)")

    if "--preview" in sys.argv:
        cols = 3
        rows = (len(made) + cols - 1) // cols
        sheet = Image.new("RGB", (cols*W, rows*H), "#DDD")
        for i, (_, p) in enumerate(made):
            sheet.paste(Image.open(p).convert("RGB"), ((i % cols)*W, (i // cols)*H))
        out = ROOT / "art" / "cards-fix" / "preview.png"
        sheet.resize((cols*320, rows*368), Image.LANCZOS).save(out)
        print("总览:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
