"""触摸回归：多指、手掌压屏、滑动都不该让点读失效。

背景：孩子的手指落在字上时，手掌常同时压在屏幕上。这时浏览器会把第二根
手指标成非主触点，并可能给第一根手指发 pointercancel、吞掉 pointerup。
原来的实现"等抬起才播放"，于是孩子觉得"点了没反应"。

现在的约定：
- 按下就出声，不等抬起；
- 每个字各锁一个触点，互不干扰；
- 接触面积过大的触点判为手掌，直接忽略；
- 长按照常弹大字卡，但报表里的点读次数要把那一次按下扣掉。

用 CDP 的 Input.dispatchTouchEvent 发真实触摸序列，不用合成事件——
合成事件测不出浏览器怎么切分 pointer。
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "file://" + str(ROOT / "dist" / "shizi-demo.html")


def run() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        cdp = ctx.new_cdp_session(pg)

        pg.goto(URL)
        pg.wait_for_timeout(1000)
        # 鲤鱼跃龙门第 2 页有「山」
        pg.locator(".tab").nth(3).click()
        pg.wait_for_timeout(320)
        pg.locator(".dot").nth(1).click()
        pg.wait_for_timeout(400)

        box = pg.locator('button.ch[data-ch="山"]').first.bounding_box()
        assert box, "该页没有「山」"
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

        def touch(points, kind):
            cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

        def counts():
            ev = pg.evaluate("ShiziTrack.events()")
            tap = len([e for e in ev if e["kind"] == "tap"])
            long_ = len([e for e in ev if e["kind"] == "long"])
            return tap, long_

        def reset():
            pg.evaluate("ShiziTrack.reset(); ShiziTrack.init()")

        def pt(x, y, i, r=10):
            return {"x": x, "y": y, "id": i, "radiusX": r, "radiusY": r, "force": 1}

        # 1 单指：基线
        reset(); base = counts()
        touch([pt(cx, cy, 1)], "touchStart")
        pg.wait_for_timeout(90)
        touch([], "touchEnd")
        pg.wait_for_timeout(350)
        assert counts()[0] - base[0] == 1, f"单指点字失败：{counts()}"
        print("✓ 单指点字 → 1 次点读")

        # 2 手掌先压屏，手指再点字（用户报的那种情况）
        reset(); base = counts()
        touch([pt(20, 790, 1, 48)], "touchStart")
        pg.wait_for_timeout(70)
        touch([pt(20, 790, 1, 48), pt(cx, cy, 2)], "touchStart")
        pg.wait_for_timeout(100)
        touch([pt(20, 790, 1, 48)], "touchEnd")
        pg.wait_for_timeout(60)
        touch([], "touchEnd")
        pg.wait_for_timeout(350)
        assert counts()[0] - base[0] == 1, f"手掌压屏时点字失效：{counts()}"
        print("✓ 手掌压屏 + 手指点字 → 仍然 1 次点读")

        # 3 点字的同时另一指碰到空白
        reset(); base = counts()
        touch([pt(cx, cy, 1)], "touchStart")
        pg.wait_for_timeout(60)
        touch([pt(cx, cy, 1), pt(360, 770, 2)], "touchStart")
        pg.wait_for_timeout(100)
        touch([pt(360, 770, 2)], "touchEnd")
        pg.wait_for_timeout(60)
        touch([], "touchEnd")
        pg.wait_for_timeout(350)
        assert counts()[0] - base[0] == 1, f"另一指碰空白导致点字失效：{counts()}"
        print("✓ 点字时另一指碰空白 → 仍然 1 次点读")

        # 4 手掌整个压在字上：不该误触发
        reset(); base = counts()
        touch([pt(cx, cy, 1, 48)], "touchStart")
        pg.wait_for_timeout(100)
        touch([], "touchEnd")
        pg.wait_for_timeout(350)
        assert counts()[0] - base[0] == 0, f"手掌压在字上被当成点击：{counts()}"
        print("✓ 手掌压在字上 → 不触发点读")

        # 5 长按：弹大字卡，报表里的点读次数不增加
        reset(); base = counts()
        touch([pt(cx, cy, 1)], "touchStart")
        pg.wait_for_timeout(560)
        touch([], "touchEnd")
        pg.wait_for_timeout(300)
        assert pg.locator("#bigWrap").is_visible(), "长按没有弹出大字卡"
        assert counts()[1] - base[1] == 1, f"没有记录 long：{counts()}"
        row = pg.evaluate("""() => {
          const rep = ShiziTrack.stats(SHIZI.lessons, SHIZI.chars, ShiziTrack.labels());
          return rep.rows.find(r => r.ch === "山") || null;
        }""")
        assert row is not None
        # 这一轮之前「山」没有点读记录，长按不该给它加数
        assert row["taps"] == 0, f"长按被计入点读：taps={row['taps']}"
        print("✓ 长按 → 弹大字卡，报表点读仍为 0")
        pg.mouse.click(20, 20)
        pg.wait_for_timeout(250)

        # 6 按住后划走：不弹大字卡
        reset(); base = counts()
        touch([pt(cx, cy, 1)], "touchStart")
        pg.wait_for_timeout(80)
        touch([pt(cx + 45, cy + 30, 1)], "touchMove")
        pg.wait_for_timeout(500)
        touch([], "touchEnd")
        pg.wait_for_timeout(300)
        assert not pg.locator("#bigWrap").is_visible(), "划走之后仍然弹了大字卡"
        print("✓ 按住后划走 → 不弹大字卡")

        assert not errors, f"页面报错：{errors}"
        b.close()
        return 0


if __name__ == "__main__":
    sys.exit(run())
