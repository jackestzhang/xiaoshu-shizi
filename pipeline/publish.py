"""把最新的单文件演示传成资料库里的一页。

    python3 pipeline/publish.py                 # 标题自动带日期和提交号
    python3 pipeline/publish.py --note "农夫贴纸版"
    python3 pipeline/publish.py --title "自定义标题.html"

每次都是新建一页，旧的留在同一个文件夹里当历史版本，想回看哪一版都能点开。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

DIST = common.ROOT / "dist"
DEMO = DIST / "shizi-demo.html"
IMPORTER = Path("/root/.codebuddy/skills/library/page/import_html.py")

# 资料库「我的资料 / 识字绘本 · 演示」
SPACE_ID = "ipxykozWM9QGDBYzWKv4zF"
FOLDER_ID = "maDewIHayOdH7AcCNeTXQW"


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=common.ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default="", help="这一版的特点，会写进标题")
    ap.add_argument("--title", default="", help="完整标题，给了就不再自动拼")
    ap.add_argument("--update", default="", help="覆盖这个已有节点的内容，而不是新建一页")
    ap.add_argument("--space-id", default=SPACE_ID)
    ap.add_argument("--parent-id", default=FOLDER_ID)
    args = ap.parse_args()

    if not DEMO.exists():
        common.die("还没有 dist/shizi-demo.html，先跑 make demo")
    if not IMPORTER.exists():
        common.die(f"找不到资料库导入工具：{IMPORTER}")

    title = args.title or " ".join(
        x for x in ("识字绘本演示", datetime.now().strftime("%Y-%m-%d"),
                    args.note or git_sha()) if x)
    if not title.endswith(".html"):
        title += ".html"

    cmd = [sys.executable, str(IMPORTER), str(DEMO), "--file-name", title,
           "--space-id", args.space_id, "--parent-id", args.parent_id]
    if args.update:
        cmd += ["--node-block-id", args.update]
    out = subprocess.run(cmd, capture_output=True, text=True)
    line = next((l for l in out.stdout.splitlines() if l.startswith("KS_IMPORT_OK")), "")
    if not line:
        common.die((out.stdout or out.stderr).strip()[:400] or "导入失败")

    info = json.loads(line.split(None, 1)[1])
    print(f"✓ 已上传：{title}  ({DEMO.stat().st_size/1024/1024:.1f} MB)")
    print(f"  {info['url']}")


if __name__ == "__main__":
    main()
