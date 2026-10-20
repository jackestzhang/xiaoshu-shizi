"""一口价检查：课程校验 + 示例数据 + 前后端口径一致。

    python tests/run_checks.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import common  # noqa: E402
import report  # noqa: E402


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def main() -> int:
    print("1) 课程校验")
    r = run([sys.executable, "pipeline/validate.py"])
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        return 1

    print("\n2) 生成示例数据")
    r = run([sys.executable, "tests/make_events.py"])
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        return 1

    print("\n3) 前后端口径比对（JS track.js vs Python report.py）")
    r = run(["node", "tests/parity.js", "tests/sample-export.json"])
    if r.returncode != 0:
        print(r.stderr)
        return 1
    js = json.loads(r.stdout)

    data = json.loads((ROOT / "tests" / "sample-export.json").read_text(encoding="utf-8"))
    py = report.compute(
        common.load_lessons(),
        common.load_curriculum(),
        data["labels"],
        data["events"],
    )

    if js == py:
        print(f"✓ 一致：{len(js['rows'])} 行 × 11 列，摘要 {js['summary']}")
    else:
        print("✗ 不一致")
        for a, b in zip(js["rows"], py["rows"]):
            if a != b:
                print("  JS:", a)
                print("  PY:", b)
        if js["summary"] != py["summary"]:
            print("  JS summary:", js["summary"])
            print("  PY summary:", py["summary"])
        return 1

    print("\n4) 示例报表")
    r = run([sys.executable, "pipeline/report.py", "--events", "tests/sample-export.json"])
    print(r.stdout.strip())
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
