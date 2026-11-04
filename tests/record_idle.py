"""录一段待机动画，压成 GIF，用来判断动起来顺不顺。

    python tests/record_idle.py [--n 24] [--out /workspace/idle.gif]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "app" / "index.html").as_uri()
TMP = Path("/tmp/idle-frames")
CHROME = "/usr/bin/chromium"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--step", type=int, default=230, help="每帧间隔 ms")
    ap.add_argument("--w", type=int, default=430)
    ap.add_argument("--h", type=int, default=880)
    ap.add_argument("--out", default=str(ROOT / "dist" / "idle.gif"))
    args = ap.parse_args()

    TMP.mkdir(parents=True, exist_ok=True)
    for f in TMP.glob("*.png"):
        f.unlink()

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": args.w, "height": args.h}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_timeout(900)
        pg.locator("#picker").click()
        pg.wait_for_timeout(250)
        idx = pg.evaluate("SHIZI.lessons.findIndex(l => l.id === 'L03')")
        pg.locator(".pick-item").nth(idx).click()
        pg.wait_for_timeout(900)
        box = pg.locator('.actor[data-id="farmer"]').bounding_box()
        pad = 46
        clip = {
            "x": max(0, box["x"] - pad),
            "y": max(0, box["y"] - pad * 1.2),
            "width": box["width"] + pad * 2,
            "height": box["height"] + pad * 1.9,
        }
        # 把播放头拨到 idle 动画的起点，保证截到的是完整一轮
        pg.evaluate("document.querySelectorAll('.actor').forEach(a=>{if(a._idle){a._idle.currentTime=0;a._idleArm&&(a._idleArm.currentTime=0);}})")
        for i in range(args.n):
            pg.screenshot(path=str(TMP / ("%03d.png" % i)), clip=clip)
            pg.wait_for_timeout(args.step)
        b.close()

    frames = [Image.open(f).convert("RGB") for f in sorted(TMP.glob("*.png"))]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=args.step, loop=0, optimize=True)
    print("GIF", out, frames[0].size, "%.0f KB" % (out.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
