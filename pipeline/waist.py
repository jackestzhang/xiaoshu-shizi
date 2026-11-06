"""给下半身素材补一截「衣摆」，堵住腰线旋转时露出来的那条白缝。

上半身绕腰点转的时候，腰线抬起的那一侧会离开下半身，露出的正好是背景
（下半身从 y≈252 才开始有像素）。逆时针转（弯腰）时这条缝在右腰，那里
本来就在画面边缘；顺时针转（直腰）时缝在左腰，白花花一条横线。

补法：把腰线下方十几行实心衣料原样往上搬，铺满 236..252。这段静止时被
上衣盖住，只有转起来才露一条边。

    python pipeline/waist.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ACTORS = common.APP / "assets" / "actors"
NAME = "L03_farmer_lo.webp"
# 取样行：腰线下方、还在整片衣料上的那一行。
SAMPLE_ROW = 258
# 往上补到哪儿。+4° 时左腰抬 10px 左右，留到 236 有余量。
FILL_TOP = 236


def main():
    p = ACTORS / NAME
    img = np.array(Image.open(p).convert("RGBA")).astype(np.float32)
    row = img[SAMPLE_ROW:SAMPLE_ROW + 1].copy()
    img[FILL_TOP:SAMPLE_ROW] = row
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(p, lossless=True)
    print("补边", NAME, FILL_TOP, "→", SAMPLE_ROW)


if __name__ == "__main__":
    main()
