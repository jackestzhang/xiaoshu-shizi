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


def pick_lesson(pg, i):
    """顶栏胶囊 + 浮层选课（替代原来的标签栏）"""
    if pg.locator("#pickerWrap").is_hidden():
        pg.locator("#picker").click()
        pg.wait_for_timeout(200)
    pg.locator(".pick-item").nth(i).click()
    pg.wait_for_timeout(380)


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

        n_lessons = pg.evaluate("SHIZI.lessons.length")
        pg.locator("#picker").click()
        pg.wait_for_timeout(250)
        assert pg.locator(".pick-item").count() == n_lessons, f"应有 {n_lessons} 节课"
        pg.locator("#pwClose").click()
        pg.wait_for_timeout(220)
        first = pg.evaluate("SHIZI.lessons.find(l => l.kind === 'story').pages[0].text")
        assert first[:8] in pg.locator("#textline").inner_text().replace("\n", ""), f"第一页文案不对：{first}"
        assert pg.locator("#scene svg, #scene img.art").count() == 1, "场景没有渲染"
        print(f"✓ 首屏：{n_lessons} 节课 / 插画或回退场景已渲染")

        # 图不可点：点画面不该产生 tap
        before = len([e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap"])
        box = pg.locator("#scene").bounding_box()
        # 右上角的天空区域没有热点，点这里才是「点画面」
        pg.mouse.click(box["x"] + box["width"] * 0.86, box["y"] + box["height"] * 0.12)
        pg.wait_for_timeout(300)
        after = len([e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap"])
        assert before == after, "点插画不应产生 tap"
        print("✓ 插画：点击画面不触发点读")

        # 图上的角色：点了要出台词气泡，但不计入点读
        assert pg.locator(".spot").count() == 3, f"热点数量不对：{pg.locator('.spot').count()}"
        sb = pg.locator('.spot[data-id="farmer"]').bounding_box()
        pg.mouse.click(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
        pg.wait_for_timeout(400)
        assert pg.locator("#bubble").is_visible(), "点角色没有出台词气泡"
        assert "农夫" in pg.locator("#bubble").inner_text(), "气泡里没有人名"
        assert pg.locator(".spot.seen").count() == 1, "点过的角色没有标记"
        spots = [e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "spot"]
        assert len(spots) == 1 and spots[0]["ch"] == "farmer", f"没有记录 spot 事件：{spots}"
        assert not [e for e in pg.evaluate("ShiziTrack.events()") if e["kind"] == "tap"], "点角色不该计点读"
        print("✓ 角色：点农夫 → 台词气泡 + spot 事件，不计点读")
        pg.screenshot(path=str(SHOTS / "01b-spot.png"))
        pg.mouse.click(20, 700)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SHOTS / "01-story.png"), full_page=True)

        # 轻点单字：只出声，不出大字
        pg.locator('button.ch[data-ch="田"]').first.click()
        pg.wait_for_timeout(500)
        assert not pg.locator("#bigWrap").is_visible(), "轻点不应该出大字"
        events = pg.evaluate("ShiziTrack.events()")
        tap = [e for e in events if e["kind"] == "tap" and e["ch"] == "田"]
        assert tap, "没有记录点击"
        print("✓ 轻点：记录 tap，延迟", tap[-1].get("lat"), "ms，未弹大字")

        # 长按：出大字，且不重复计入点击
        el = pg.locator('button.ch[data-ch="草"]').first
        box = el.bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.wait_for_timeout(560)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        assert pg.locator("#bigWrap").is_visible(), "长按没有弹出大字"
        assert pg.locator("#bigGlyph").inner_text() == "草"
        # 按下即出声，所以长按会先落一条 tap；报表口径要把这条扣掉
        row = pg.evaluate("""() => {
          const rep = ShiziTrack.stats(SHIZI.lessons, SHIZI.chars, ShiziTrack.labels());
          return rep.rows.find(r => r.ch === "草") || null;
        }""")
        assert row is not None, "报表里没有「草」"
        assert row["taps"] == 0, f"长按不应计入点读，实际 taps={row['taps']}"
        print("✓ 长按：出大字，报表里点读次数仍为 0")
        pg.screenshot(path=str(SHOTS / "02-bigchar.png"))
        pg.mouse.click(20, 20)
        pg.wait_for_timeout(300)

        # 翻页
        pg.locator("#next").click()
        pg.wait_for_timeout(400)
        second = pg.evaluate("SHIZI.lessons.find(l => l.kind === 'story').pages[1].text")
        assert second[:8] in pg.locator("#textline").inner_text().replace("\n", ""), f"第 2 页文案不对：{second}"
        print("✓ 翻页：第 2 页文案正确")
        pg.locator("#prev").click()
        pg.wait_for_timeout(300)

        # 字卡课
        pick_lesson(pg, 0)
        assert pg.locator(".card").count() == 6, "字卡数量不对"
        pg.locator('.card[data-ch="兔"] .glyph').click()
        pg.wait_for_timeout(400)
        print("✓ 字卡课：6 张，点字有声")
        pg.screenshot(path=str(SHOTS / "03-cards.png"), full_page=True)

        # 回到绘本，打开家长面板
        pick_lesson(pg, 2)
        pg.locator("#parentBtn").click()
        pg.wait_for_timeout(350)
        rows = pg.locator("table.stat tbody tr").count()
        expected = pg.evaluate("ShiziTrack.allChars(SHIZI.lessons).length")
        assert rows == expected, f"面板应有 {expected} 行，实际 {rows}"
        print(f"✓ 家长面板：{rows} 行 ·", pg.locator(".summary").inner_text().replace("\n", " "))
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

        # 每一课的每一页：正文不能撑破卡片（长句最容易出问题）
        bad = []
        total = 0
        m.evaluate("localStorage.clear()")
        m.reload(); m.wait_for_timeout(500)

        # 同一页有重复字时，只高亮被点的那一个
        pick_lesson(m, 3)
        idx = m.evaluate("""() => {
          const els = [...document.querySelectorAll('#textline .ch')];
          const seen = {};
          for (let i = 0; i < els.length; i++) {
            const c = els[i].dataset.ch;
            if (seen[c] !== undefined) return {ch: c, n: els.filter(e => e.dataset.ch === c).length};
            seen[c] = i;
          }
          return null;
        }""")
        assert idx, "该页没有重复字，无法验证同字高亮"
        m.locator('button.ch[data-ch="%s"]' % idx["ch"]).first.click()
        m.wait_for_timeout(250)
        lit = m.locator(".ch.lit").count()
        assert lit == 1, f"同字应只亮 1 个，实际 {lit}"
        print(f"✓ 同字：页面有 {idx['n']} 个「{idx['ch']}」，只高亮被点的 1 个")

        n_lessons = m.evaluate("SHIZI.lessons.length")
        for li in range(n_lessons):
            pick_lesson(m, li)
            if m.locator("#textline").count() == 0:
                continue
            pages = m.evaluate("SHIZI.lessons[%d].pages.length" % li)
            for pi in range(pages):
                if pi:
                    m.locator(".dot").nth(pi).click(); m.wait_for_timeout(220)
                r = m.evaluate("""() => {
                  const b = document.getElementById('textline');
                  if (!b) return null;
                  return {sw: b.scrollWidth, cw: b.clientWidth};
                }""")
                total += 1
                if r and r["sw"] > r["cw"] + 1:
                    bad.append((li + 1, pi + 1, r["sw"], r["cw"]))
        assert not bad, f"正文溢出卡片：{bad}"
        print(f"✓ 手机 390px：无横向溢出 · {total} 页正文均未撑破卡片")
        m.screenshot(path=str(SHOTS / "06-mobile.png"), full_page=True)

        assert not errors, f"页面报错：{errors}"
        print("\n全部通过 · 截图在 tests/shots/")
        b.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
