"""打包成可以塞进 Android assets 的 zip。

    python pipeline/pack.py
    → dist/shizi-web.zip  (app/ + manifest.json)

manifest 带每个文件的 sha1，装新课/同步时可以先校验再替换，
不会出现"装了一半"的课程。
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

DIST = common.ROOT / "dist"


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> None:
    DIST.mkdir(exist_ok=True)
    lessons = common.load_lessons()
    files = sorted(p for p in common.APP.rglob("*") if p.is_file())
    manifest = {
        "version": 1,
        "builtAt": common.stamp(),
        "lessons": [
            {"id": l["id"], "title": l["title"], "kind": l["kind"],
             "chars": common.lesson_chars(l)}
            for l in lessons
        ],
        "files": {str(p.relative_to(common.APP)): sha1(p) for p in files},
        "totalBytes": sum(p.stat().st_size for p in files),
    }

    out = DIST / "shizi-web.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(common.APP))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"✓ {out.relative_to(common.ROOT)} · {out.stat().st_size/1024:.0f} KB · {len(files)} 个文件")
    print(f"  {len(manifest['lessons'])} 节课 · {manifest['totalBytes']/1024:.0f} KB 解压后")


if __name__ == "__main__":
    main()
