"""拍一组农夫舞锄的连拍，用来判断关节动作像不像。

    python tests/shoot_hoe.py [--ms 0,120,240,...]

输出到 tests/shots/hoe-*.png，再拼一张 contact sheet 到 tests/shots/hoe-sheet.png。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "app" / "index.html").as_uri()
SHOTS = ROOT / "tests" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
CHROME = "/usr/bin/chromium"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ms", default="0,100,200,320,440,560,700,860,1000")
    ap.add_argument("--w", type=int, default=430)
    ap.add_argument("--h", type=int, default=880)
    args = ap.parse_args()
    marks = [int(x) for x in args.ms.split(",")]

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": args.w, "height": args.h},
                            device_scale_factor=3)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(900)
        # 选到守株待兔
        pg.locator("#picker").click()
        pg.wait_for_timeout(250)
        idx = pg.evaluate("SHIZI.lessons.findIndex(l => l.id === 'L03')")
        pg.locator(".pick-item").nth(idx).click()
        pg.wait_for_timeout(700)
        # 关掉语音，免得截图中途被打断
        pg.evaluate("document.querySelectorAll('audio').forEach(a=>a.muted=true)")

        box = pg.locator('.actor[data-id="farmer"]').bounding_box()
        print("farmer box", box)
        pad = 60
        clip = {
            "x": max(0, box["x"] - pad),
            "y": max(0, box["y"] - pad),
            "width": min(args.w - max(0, box["x"] - pad), box["width"] + pad * 2),
            "height": box["height"] + pad * 1.4,
        }
        files = []
        prev = 0
        pg.locator(".actor[data-id=\"farmer\"]").click(force=True)
        t0 = pg.evaluate("performance.now()")
        for m in marks:
            if m > prev:
                pg.wait_for_timeout(m - prev)
                prev = m
            f = SHOTS / ("hoe-%04d.png" % m)
            pg.screenshot(path=str(f), clip=clip)
            files.append((m, f))
        if errs:
            print("PAGEERROR", errs)
        b.close()

    ims = [(m, Image.open(f).convert("RGB")) for m, f in files]
    w, h = ims[0][1].size
    scale = 300 / w
    tw, th = int(w * scale), int(h * scale)
    sheet = Image.new("RGB", (tw * len(ims) + 8 * (len(ims) - 1), th), (255, 255, 255))
    for i, (m, im) in enumerate(ims):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (i * (tw + 8), 0))
    sheet.save(SHOTS / "hoe-sheet.png")
    print("contact sheet", SHOTS / "hoe-sheet.png", sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
