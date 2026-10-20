"""生成一份可复现的示例数据，用于报表和前后端一致性测试。

不是随手编的数字：按"三天里读了 2 页、复习了一次、做了一次测验"来排，
其中包含一次 20ms 的误触会话，用来验证曝光撤回。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    base = datetime(2026, 10, 14, 18, 40, 0)
    events = []

    def add(kind, sid, ts, **kw):
        e = {"kind": kind, "ts": int(ts.timestamp() * 1000), "sid": sid,
             "day": ts.strftime("%Y-%m-%d")}
        e.update(kw)
        events.append(e)

    def session(sid, start, dur, pages):
        """pages: [(lesson, page, [chars], [tap list])]"""
        add("start", sid, start)
        for lesson, page, chars, taps in pages:
            for ch in chars:
                add("exp", sid, start + timedelta(seconds=2), lesson=lesson, page=page, ch=ch)
            for ch, count, lat in taps:
                for k in range(count):
                    add("tap", sid, start + timedelta(seconds=8 + k), lesson=lesson, page=page, ch=ch, lat=lat)
        add("end", sid, start + timedelta(seconds=dur), dur=dur * 1000)

    # 第 1 天：第一次读，山点了 2 下，水 1 下，小兔连点 3 下
    session("s1", base, 240, [
        ("L03", 1, ["山", "边", "有", "树", "水"], [("山", 2, 38), ("水", 1, 41)]),
        ("L03", 2, ["小", "兔", "跑", "来", "撞", "上", "树"], [("兔", 3, 36), ("树", 1, 44)]),
    ])

    # 第 2 天：复习第 1 页，水又点了 2 下；做了一次 3 题测验
    d2 = base + timedelta(days=1, minutes=30)
    session("s2", d2, 180, [
        ("L03", 1, ["山", "边", "有", "树", "水"], [("山", 1, 35), ("树", 1, 39), ("水", 2, 37)]),
    ])
    for ch, ok in [("山", True), ("树", False), ("水", True)]:
        add("quiz", "s2", d2 + timedelta(seconds=120), lesson="L03", page=0, ch=ch, ok=ok)

    # 第 3 天：字卡课，兔连点 5 下（新鲜感），并看了一次大字
    d3 = base + timedelta(days=2, hours=-1)
    session("s3", d3, 300, [
        ("L01", 0, ["兔", "树", "跑", "来", "小", "上"], [("兔", 5, 33), ("小", 1, 40)]),
    ])
    add("long", "s3", d3 + timedelta(seconds=60), lesson="L01", page=0, ch="兔")

    # 一次 20ms 的误触：只产生曝光，没有点击，应当被撤回
    s4 = d3 + timedelta(minutes=6)
    add("start", "s4", s4)
    for ch in ["山", "边", "有", "树", "水"]:
        add("exp", "s4", s4 + timedelta(milliseconds=5), lesson="L03", page=1, ch=ch)
    add("end", "s4", s4 + timedelta(milliseconds=20), dur=20)

    # 第 4 天：只翻到第 3 页，没点；做了 2 题测验，兔都没答对
    d5 = base + timedelta(days=3, hours=1)
    session("s5", d5, 200, [
        ("L03", 1, ["山", "边", "有", "树", "水"], []),
        ("L03", 3, ["他", "等", "兔", "没", "来"], []),
    ])
    for ok in (False, False):
        add("quiz", "s5", d5 + timedelta(seconds=150), lesson="L03", page=0, ch="兔", ok=ok)

    payload = {
        "version": 1,
        "exportedAt": "2026-10-18T12:00:00.000Z",
        "events": events,
        "labels": {"树": "not", "山": "know"},
    }
    out = ROOT / "tests" / "sample-export.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {out.relative_to(ROOT)} · {len(events)} 条事件")


if __name__ == "__main__":
    main()
