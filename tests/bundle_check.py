"""单文件版在"沙箱 + srcdoc"里的回归。

预览器常用这种方式渲染产物：CSS/JS 能进去，但运行时用相对路径请求的音频进不去。
这里把 shizi-demo.html 塞进 sandbox="allow-scripts" 的 iframe，点一个字，
必须出现 tap 事件且 lat 有值（说明真的开始播放了）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dist" / "shizi-demo.html").read_text(encoding="utf-8")


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1150, "height": 950})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("about:blank")
        pg.evaluate("""(html) => {
            const f = document.createElement('iframe');
            f.id = 'f';
            f.setAttribute('sandbox', 'allow-scripts');
            f.style.width = '1120px';
            f.style.height = '900px';
            f.style.border = '0';
            document.body.style.margin = '0';
            document.body.appendChild(f);
            f.srcdoc = html;
        }""", HTML)
        pg.wait_for_timeout(1800)

        frame = next(f for f in pg.frames if f != pg.main_frame)
        assert frame.evaluate("!!window.SHIZI"), "单文件里没有数据，脚本没跑起来"
        target = frame.evaluate("""() => {
          const els = [...document.querySelectorAll('#textline .ch')];
          return els.length ? els[0].dataset.ch : null;
        }""")
        assert target, "首屏没有可点的字"
        frame.locator('button.ch[data-ch="%s"]' % target).first.click()
        pg.wait_for_timeout(1000)

        events = frame.evaluate("ShiziTrack.events()")
        taps = [e for e in events if e["kind"] == "tap"]
        assert taps and taps[-1].get("lat") is not None, f"没有播放成功：{events}"
        assert not errors, f"页面报错：{errors}"
        print(f"✓ 沙箱 srcdoc：点击「{target}」→ 播放延迟 {taps[-1]['lat']}ms，无外部请求、无报错")
        b.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
