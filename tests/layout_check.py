"""定版检查：一屏放下，不滚动、不裁切、不溢出。

覆盖 11 寸 / 12.9 寸平板的横竖屏，外加手机横竖屏。
每个断点都跑真实布局，量：

- 页面本身不能有滚动（scrollWidth/scrollHeight 不超视口）；
- 图框必须完整落在舞台里；
- 正文必须完整落在文字卡里（宽和高都不许溢出）；
- 每个字的点击区高度不小于 34px（孩子手指比成人粗）。

    python tests/layout_check.py
截图写到 tests/shots/layout-*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "app" / "index.html").as_uri()
SHOTS = ROOT / "tests" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

CHROME = "/usr/bin/chromium"

DEVICES = [
    ("ipad11-portrait", 834, 1194),
    ("ipad11-landscape", 1194, 834),
    ("ipad13-portrait", 1024, 1366),
    ("ipad13-landscape", 1366, 1024),
    ("phone-portrait", 390, 844),
    ("phone-landscape", 844, 390),
]

# 页面里量一次，返回所有越界项
PROBE = """() => {
  const out = {scroll: {}, boxes: {}, text: [], hit: []};
  out.scroll.w = document.documentElement.scrollWidth;
  out.scroll.h = document.documentElement.scrollHeight;
  out.scroll.iw = window.innerWidth;
  out.scroll.ih = window.innerHeight;

  const stage = document.querySelector('.stage');
  const card = document.querySelector('.scene-card');
  if (stage && card) {
    const s = stage.getBoundingClientRect(), c = card.getBoundingClientRect();
    out.boxes.stage = {w: s.width, h: s.height};
    out.boxes.card = {w: c.width, h: c.height};
    out.boxes.cardOver = (c.width > s.width + 1 || c.height > s.height + 1);
  }

  const box = document.getElementById('textline');
  if (box) {
    const b = box.getBoundingClientRect();
    out.boxes.text = {w: b.width, h: b.height, bottom: b.bottom};
    let top = Infinity, bot = -Infinity, left = Infinity, right = -Infinity;
    box.querySelectorAll('.phrase').forEach(p => {
      const r = p.getBoundingClientRect();
      if (!r.width) return;
      top = Math.min(top, r.top); bot = Math.max(bot, r.bottom);
      left = Math.min(left, r.left); right = Math.max(right, r.right);
    });
    if (isFinite(top)) {
      out.text.push({
        w: right - left, h: bot - top,
        overW: (right - left) > b.width + 1,
        overH: (bot - top) > b.height + 1
      });
      out.boxes.ink = {top, bottom: bot, left, right};
    }
    out.boxes.fs = getComputedStyle(box).getPropertyValue('--fs').trim();
  }

  document.querySelectorAll('button.ch').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.height && r.height < 34) out.hit.push({ch: el.dataset.ch, h: +r.height.toFixed(1)});
  });
  return out;
}"""


def check_page(pg, tag: str, w: int, h: int, wh: tuple[int, int]) -> list[str]:
    bad: list[str] = []
    r = pg.evaluate(PROBE)
    if r["scroll"]["w"] > r["scroll"]["iw"] + 1:
        bad.append(f"横向可滚动 {r['scroll']['w']} > {r['scroll']['iw']}")
    if r["scroll"]["h"] > r["scroll"]["ih"] + 1:
        bad.append(f"纵向可滚动 {r['scroll']['h']} > {r['scroll']['ih']}")
    for t in r["text"]:
        if t["overW"]:
            bad.append(f"正文超宽 {t['w']:.0f}")
        if t["overH"]:
            bad.append(f"正文超高 {t['h']:.0f} > {r['boxes']['text']['h']:.0f}")
    if r["boxes"].get("cardOver"):
        bad.append("图框超出舞台 %.0f/%.0f vs %.0f/%.0f" % (
            r["boxes"]["card"]["w"], r["boxes"]["card"]["h"],
            r["boxes"]["stage"]["w"], r["boxes"]["stage"]["h"]))
    ink = r["boxes"].get("ink")
    if ink and ink["bottom"] > h + 1:
        bad.append(f"正文掉出屏幕 {ink['bottom']:.0f} > {h}")
    if r["hit"]:
        bad.append("点击区太矮：" + "、".join(f"{x['ch']}{x['h']}px" for x in r["hit"][:4]))
    return bad


def swipe_test(b, w: int, h: int) -> list[str]:
    """真的用手指滑一下：页面不许动。"""
    bad: list[str] = []
    ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=True, is_mobile=True)
    pg = ctx.new_page()
    pg.goto(URL)
    pg.wait_for_timeout(600)
    cdp = ctx.new_cdp_session(pg)
    before = pg.locator(".scene-card").bounding_box()

    def swipe(dx: int, dy: int):
        x, y = w / 2, h * 0.55
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart",
                 "touchPoints": [{"x": x, "y": y, "id": 1, "radiusX": 9, "radiusY": 9}]})
        for i in range(1, 16):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints":
                     [{"x": x + dx * i / 15, "y": y + dy * i / 15, "id": 1, "radiusX": 9, "radiusY": 9}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        pg.wait_for_timeout(320)

    swipe(0, -260)      # 往上推
    swipe(0, 260)       # 往下拽（iOS 上会触发橡皮筋）
    swipe(-260, 0)      # 往左划
    after = pg.locator(".scene-card").bounding_box()
    moved = max(abs(after["x"] - before["x"]), abs(after["y"] - before["y"]))
    if moved > 1:
        bad.append(f"滑动后版面位移 {moved:.1f}px")
    pos = pg.evaluate("[window.scrollY, document.scrollingElement.scrollTop, "
                      "document.documentElement.scrollLeft]")
    if any(abs(v) > 0.5 for v in pos):
        bad.append(f"页面被滚动了 {pos}")
    ctx.close()
    return bad


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        for name, w, h in DEVICES:
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg = ctx.new_page()
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.evaluate("localStorage.clear()")
            pg.reload()
            pg.wait_for_timeout(500)

            n = pg.evaluate("SHIZI.lessons.length")
            pages = 0
            for li in range(n):
                pg.locator(".tab").nth(li).click()
                pg.wait_for_timeout(160)
                if pg.locator("#textline").count() == 0:
                    bad = check_page(pg, name, w, h, (w, h))
                    if bad:
                        failures.append(f"[{name}] 第 {li+1} 课（字卡）：" + "；".join(bad))
                    continue
                total = pg.evaluate(f"SHIZI.lessons[{li}].pages.length")
                for pi in range(total):
                    if pi:
                        pg.locator(".dot").nth(pi).click()
                        pg.wait_for_timeout(150)
                    bad = check_page(pg, name, w, h, (w, h))
                    pages += 1
                    if bad:
                        failures.append(f"[{name}] 第 {li+1} 课第 {pi+1} 页：" + "；".join(bad))

            # 截一张有代表性的：故事课第一页 + 字卡
            pg.locator(".tab").nth(2).click()
            pg.wait_for_timeout(260)
            pg.screenshot(path=str(SHOTS / f"layout-{w}x{h}.png"))
            fs = pg.evaluate("getComputedStyle(document.getElementById('textline')).getPropertyValue('--fs')")
            print(f"· {name:17s} {w}×{h}  故事课 {pages // n} 页均通过  字号"
                  f"{fs.strip() or '-'}")
            if errs:
                failures.append(f"[{name}] 页面报错：{errs}")
            ctx.close()

        # 滑动防误触：平板上划一下，版面必须纹丝不动
        for w, h, tag in [(834, 1194, "竖屏"), (1194, 834, "横屏")]:
            bad = swipe_test(b, w, h)
            print(f"· 滑动测试 {w}×{h} {tag}：" + ("不动 ✓" if not bad else "；".join(bad)))
            failures += [f"[滑动 {tag}] {x}" for x in bad]
        b.close()

    if failures:
        print("\n定版失败：")
        for f in failures:
            print("  ✗", f)
        return 1
    print("\n全部通过：一屏放下，无滚动、无裁切、无溢出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
