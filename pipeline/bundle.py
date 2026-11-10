"""把 app/ 打成一个自包含 HTML。

预览器常把页面塞进 srcdoc/沙箱里跑：CSS、JS 能被重写，但代码在运行时
用相对路径 new Audio("assets/audio/x.mp3") 请求的音频不会。这个脚本把
样式、脚本、数据、31 段语音全部内联，运行时零外部请求。

    python pipeline/bundle.py
    → dist/shizi-demo.html
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

DIST = common.ROOT / "dist"


def main() -> None:
    DIST.mkdir(exist_ok=True)
    html = (common.APP / "index.html").read_text(encoding="utf-8")

    # 样式按 index.html 的引用顺序内联；app.css / dialog.css 都可能在，
    # 后者依赖前者，不能调换顺序。index.html 没引用的样式直接跳过。
    for name in ("app.css", "dialog.css"):
        path = common.APP / name
        tag = f'<link rel="stylesheet" href="{name}">'
        if tag not in html:
            continue
        if not path.exists():
            common.die(f"index.html 引用了 {name}，但文件不存在")
        html = html.replace(tag, "<style>\n" + path.read_text(encoding="utf-8") + "\n</style>")

    data_js = (common.APP / "data.js").read_text(encoding="utf-8")

    # 音频与插画 → base64 data URI（先收集，再一次性替换）
    paths = sorted(set(re.findall(r'assets/(?:audio/[a-f0-9]+\.mp3|(?:art|actors|picto|cards)/[^"]+\.webp)', data_js)))
    total = 0
    n_img = 0
    for rel in paths:
        f = common.APP / rel
        mime = "audio/mpeg" if rel.endswith(".mp3") else "image/webp"
        if mime.startswith("image"):
            n_img += 1
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        data_js = data_js.replace('"' + rel + '"', f'"data:{mime};base64,' + b64 + '"')
        total += f.stat().st_size

    js = {"data.js": data_js}
    # dialog.js 必须在 app.js 之前执行，和 index.html 的引用顺序一致。
    for name in ("sprites.js", "scene.js", "track.js", "dialog.js", "app.js"):
        if name == "dialog.js" and f'<script src="{name}"></script>' not in html:
            continue
        js[name] = (common.APP / name).read_text(encoding="utf-8")

    for name, code in js.items():
        tag = f'<script src="{name}"></script>'
        if tag not in html:
            common.die(f"index.html 里找不到 {tag}")
        html = html.replace(tag, "<script>\n" + code + "\n</script>")

    html = html.replace("<head>", "<head>\n<!-- 自包含构建：音视频/样式/脚本全部内联，无外部请求 -->")

    out = DIST / "shizi-demo.html"
    common.write_atomic(out, html)
    print(f"✓ {out.relative_to(common.ROOT)} · {out.stat().st_size/1024:.0f} KB")
    print(f"  内联资源 {len(paths)} 个（其中插画 {n_img} 张）/ {total/1024:.0f} KB（base64 后约 {total*4/3/1024:.0f} KB）")


if __name__ == "__main__":
    main()
