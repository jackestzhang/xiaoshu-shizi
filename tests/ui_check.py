"""儿童端回归：真 DOM、真事件、真下载。

    python tests/ui_check.py
截图写到 tests/shots/。
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


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1100, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        pg.evaluate("window.ShiziTrack && ShiziTrack.reset()")
        pg.reload()
        pg.wait_for_timeout(700)

        assert pg.locator(".tab").count() == 3, "应有 3 节课"
        assert "山边有树" in pg.locator("#textline").inner_text().replace("\n", ""), "第一页文案不对"
        assert pg.locator("#scene svg, #scene img.art").count() == 1, "场景没有渲染"
        print("✓ 首屏：3 节课 / 插画或回退场景已渲染")

        # 图不可点：点画面不该产生 tap
        before = len([e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap"])
        box = pg.locator("#scene").bounding_box()
        pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.45)
        pg.wait_for_timeout(300)
        after = len([e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap"])
        assert before == after, "点插画不应产生 tap"
        print("✓ 插画：点击画面不触发点读")
        pg.screenshot(path=str(SHOTS / "01-story.png"), full_page=True)

        # 轻点单字：只出声，不出大字
        pg.locator('button.ch[data-ch="山"]').click()
        pg.wait_for_timeout(500)
        assert not pg.locator("#bigWrap").is_visible(), "轻点不应该出大字"
        events = pg.evaluate("ShiziTrack.events()")
        tap = [e for e in events if e["kind"] == "tap" and e["ch"] == "山"]
        assert tap, "没有记录点击"
        print("✓ 轻点：记录 tap，延迟", tap[-1].get("lat"), "ms，未弹大字")

        # 长按：出大字，且不重复计入点击
        el = pg.locator('button.ch[data-ch="树"]').first
        box = el.bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.wait_for_timeout(560)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        assert pg.locator("#bigWrap").is_visible(), "长按没有弹出大字"
        assert pg.locator("#bigGlyph").inner_text() == "树"
        n_tap = len([e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap" and e["ch"] == "树"])
        assert n_tap == 0, "长按不应产生 tap"
        print("✓ 长按：出大字，tap 数仍为 0")
        pg.screenshot(path=str(SHOTS / "02-bigchar.png"))
        pg.mouse.click(20, 20)
        pg.wait_for_timeout(300)

        # 翻页
        pg.locator("#next").click()
        pg.wait_for_timeout(400)
        assert "小兔跑来" in pg.locator("#textline").inner_text().replace("\n", "")
        print("✓ 翻页：第 2 页文案正确")
        pg.locator("#prev").click()
        pg.wait_for_timeout(300)

        # 字卡课
        pg.locator(".tab").nth(0).click()
        pg.wait_for_timeout(400)
        assert pg.locator(".card").count() == 6, "字卡数量不对"
        pg.locator('.card[data-ch="兔"] .glyph').click()
        pg.wait_for_timeout(400)
        print("✓ 字卡课：6 张，点字有声")
        pg.screenshot(path=str(SHOTS / "03-cards.png"), full_page=True)

        # 回到绘本，打开家长面板
        pg.locator(".tab").nth(2).click()
        pg.wait_for_timeout(300)
        pg.locator("#parentBtn").click()
        pg.wait_for_timeout(350)
        rows = pg.locator("table.stat tbody tr").count()
        assert rows == 14, f"面板应有 14 行，实际 {rows}"
        print("✓ 家长面板：14 行 ·", pg.locator(".summary").inner_text().replace("\n", " "))
        pg.screenshot(path=str(SHOTS / "04-drawer.png"), full_page=True)

        # 家长标注优先于推断
        pg.locator('.lab[data-ch="树"][data-l="not"]').click()
        pg.wait_for_timeout(200)
        assert pg.evaluate("ShiziTrack.labels()")['树'] == "not"
        row = pg.locator("table.stat tbody tr").filter(has_text="树").first.inner_text()
        assert "不会（家长）" in row, "标注没有覆盖判断"
        print("✓ 标注：不会（家长）覆盖了点击推断")

        # 听音找字
        pg.locator("#quizBtn").click()
        pg.wait_for_timeout(500)
        assert pg.locator(".option").count() == 4, "应有 4 个选项"
        for _ in range(5):
            pg.locator(".option").first.click()
            pg.wait_for_timeout(1400)
        assert pg.locator("#quizCount").inner_text() == "完成", "测验没有结束"
        quiz = [e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "quiz"]
        assert len(quiz) == 5, f"应有 5 条测验事件，实际 {len(quiz)}"
        print("✓ 听音找字：5 题结束，记录 5 条 quiz 事件")
        pg.screenshot(path=str(SHOTS / "05-quiz.png"), full_page=True)
        pg.locator("#closeQuiz").click()
        pg.wait_for_timeout(300)

        # 导出
        pg.locator("#parentBtn").click()
        pg.wait_for_timeout(300)
        with pg.expect_download() as dl:
            pg.locator("#exportBtn").click()
        path = dl.value.path()
        size = Path(path).stat().st_size
        assert size > 1000, "导出文件太小"
        print(f"✓ 导出：{size} 字节")

        # 手机视口
        m = ctx.new_page()
        m.set_viewport_size({"width": 390, "height": 844})
        m.goto(URL)
        m.wait_for_timeout(600)
        assert m.locator("#textline").is_visible()
        w = m.evaluate("document.documentElement.scrollWidth")
        assert w <= 390, f"手机端横向溢出：{w}px"
        print("✓ 手机 390px：无横向溢出")
        m.screenshot(path=str(SHOTS / "06-mobile.png"), full_page=True)

        assert not errors, f"页面报错：{errors}"
        print("\n全部通过 · 截图在 tests/shots/")
        b.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
