"""象形卡回归：长按出大字 → 点一下变图 → 再点回字。

同时验证两件事：
1. 有象形图的字，卡片上有提示，点击能切换，图片真的加载出来；
2. 没有象形图的字，不显示提示，点击也不会变成空白。
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = "file://" + str(ROOT / "dist" / "shizi-demo.html")


def longpress(pg, sel: str, ms: int = 520) -> None:
    box = pg.locator(sel).first.bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pg.mouse.down()
    pg.wait_for_timeout(ms)
    pg.mouse.up()
    pg.wait_for_timeout(300)


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1100, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(900)

        # ---- 有象形图：山（鲤鱼跃龙门第 2 页）----
        pg.locator(".tab").nth(3).click()
        pg.wait_for_timeout(350)
        pg.locator(".dot").nth(1).click()
        pg.wait_for_timeout(350)
        assert pg.locator('button.ch[data-ch="山"]').count() > 0, "该页没有「山」"

        longpress(pg, 'button.ch[data-ch="山"]')
        assert pg.locator("#bigWrap").is_visible(), "长按没有出现大字卡"
        assert pg.locator("#bigHint").is_visible(), "有象形图的字没有显示点击提示"

        pg.locator("#bigCard").click()
        pg.wait_for_timeout(450)
        assert pg.locator("#bigPic").is_visible(), "点击后没有显示象形图"
        assert not pg.locator("#bigGlyph").is_visible(), "显示象形图时大字应隐藏"
        nat = pg.eval_on_selector("#bigPic", "el => [el.naturalWidth, el.complete]")
        assert nat[1] and nat[0] >= 320, f"象形图没加载好：{nat}"
        assert not pg.locator("#bigHint").is_visible(), "看图时不应再显示提示"

        pg.locator("#bigCard").click()
        pg.wait_for_timeout(300)
        assert pg.locator("#bigGlyph").is_visible(), "再点一下没有回到大字"
        print(f"✓ 象形卡：长按「山」→ 点一下出图（{nat[0]}px）→ 再点回字")

        pg.mouse.click(20, 20)
        pg.wait_for_timeout(250)
        assert not pg.locator("#bigWrap").is_visible(), "点空白没有关闭卡片"

        # ---- 没有象形图：清（第 1 页）----
        pg.locator(".dot").nth(0).click()
        pg.wait_for_timeout(300)
        longpress(pg, 'button.ch[data-ch="清"]')
        assert pg.locator("#bigWrap").is_visible(), "长按没有出现大字卡"
        assert not pg.locator("#bigHint").is_visible(), "无象形图的字不应显示提示"
        pg.locator("#bigCard").click()
        pg.wait_for_timeout(300)
        assert pg.locator("#bigGlyph").is_visible(), "无图时点击不该切换"
        assert not pg.locator("#bigPic").is_visible(), "无图时不该显示空图片"
        print("✓ 无象形图的字：不显示提示，点击也不切换")

        assert not errors, f"页面报错：{errors}"
        b.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
