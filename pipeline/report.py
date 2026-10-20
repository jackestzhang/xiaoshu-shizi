"""离线报表：读家长导出的 JSON，算和 App 完全一致的指标。

        python pipeline/report.py --events ~/Downloads/shizi-events.json
        python pipeline/report.py --events ... --json   # 给 parity 测试用
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

RANK = {
    "不会（家长）": 0, "测验未过": 1, "反复点": 2, "?（家长）": 3,
    "新鲜感": 4, "待观察": 5, "从不点": 6, "没看到": 7, "会（家长）": 8,
}


def day_of(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


def compute(lessons: list[dict], char_meta: dict, labels: dict, events: list[dict]) -> dict:
    sess: dict[str, dict] = {}
    for e in events:
        s = sess.setdefault(e["sid"], {"dur": None, "taps": 0})
        if e["kind"] == "end":
            s["dur"] = e.get("dur")
        if e["kind"] == "tap":
            s["taps"] += 1
    bad = {sid for sid, s in sess.items() if s["dur"] is not None and s["dur"] < 50 and s["taps"] == 0}
    kept = [e for e in events if not (e["kind"] == "exp" and e["sid"] in bad)]

    chars = common.unique([ch for l in lessons for ch in common.lesson_chars(l)])
    rows = {ch: {"ch": ch, "exp": 0, "taps": 0, "days": set(), "perSid": {}, "quizN": 0, "quizOK": 0, "last": 0}
            for ch in chars}
    lats = []
    for e in kept:
        ch = e.get("ch")
        if not ch or ch not in rows:
            continue
        m = rows[ch]
        if e["kind"] == "exp":
            m["exp"] += 1
        elif e["kind"] == "tap":
            m["taps"] += 1
            m["perSid"][e["sid"]] = m["perSid"].get(e["sid"], 0) + 1
            if isinstance(e.get("lat"), (int, float)):
                lats.append(e["lat"])
        elif e["kind"] == "quiz":
            m["quizN"] += 1
            m["quizOK"] += 1 if e.get("ok") else 0
        if e.get("day"):
            m["days"].add(e["day"])
        m["last"] = max(m["last"], e.get("ts", 0))

    out = []
    for ch, m in rows.items():
        rate = m["taps"] / m["exp"] if m["exp"] else 0.0
        days = len(m["days"])
        max_single = max(m["perSid"].values()) if m["perSid"] else 0
        acc = (m["quizOK"] / m["quizN"]) if m["quizN"] else None
        label = labels.get(ch, "")
        if label == "know":
            judge = "会（家长）"
        elif label == "not":
            judge = "不会（家长）"
        elif label == "q":
            judge = "?（家长）"
        elif m["quizN"] >= 2 and acc is not None and acc < 0.6:
            judge = "测验未过"
        elif days >= 2 and rate >= 0.6:
            judge = "反复点"
        elif max_single >= 3 and days <= 1:
            judge = "新鲜感"
        elif m["exp"] == 0:
            judge = "没看到"
        elif m["taps"] == 0 and m["exp"] >= 3:
            judge = "从不点"
        else:
            judge = "待观察"
        meta = char_meta.get(ch, {})
        out.append({
            "ch": ch, "exp": m["exp"], "taps": m["taps"], "rate": round(rate, 4),
            "days": days, "maxSingle": max_single, "quizN": m["quizN"], "quizOK": m["quizOK"],
            "acc": None if acc is None else round(acc, 4), "judge": judge, "label": label,
            "pinyin": meta.get("pinyin", ""), "word": meta.get("word", ""),
        })
    out.sort(key=lambda r: (RANK[r["judge"]], -r["taps"], r["ch"]))

    today = day_of(int(datetime.now().timestamp() * 1000))
    lats.sort()
    return {
        "rows": out,
        "summary": {
            "totalChars": len(rows),
            "seenChars": sum(1 for r in out if r["exp"] > 0),
            "events": len(kept),
            "sessions": len(sess),
            "latency": int(lats[len(lats) // 2]) if lats else None,
            "todayTaps": sum(1 for e in kept if e["kind"] == "tap" and e.get("day") == today),
            "quizN": sum(1 for e in kept if e["kind"] == "quiz"),
            "quizOK": sum(1 for e in kept if e["kind"] == "quiz" and e.get("ok")),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True, help="家长面板导出的 JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.events).read_text(encoding="utf-8"))
    events = data.get("events", data if isinstance(data, list) else [])
    labels = data.get("labels", {}) if isinstance(data, dict) else {}
    lessons = common.load_lessons()
    char_meta = common.load_curriculum()
    res = compute(lessons, char_meta, labels, events)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    s = res["summary"]
    lat = f"{s['latency']}ms" if s["latency"] is not None else "—"
    print(f"看过 {s['seenChars']}/{s['totalChars']} 字 · {s['sessions']} 次会话 · {s['events']} 条事件 · 点读延迟中位数 {lat}")
    print("=" * 82)
    print(f"{'字':<2}{'拼音':<8}{'出现':>4}{'点了':>4}{'点击率':>7}{'跨天':>4}{'单次':>4}  {'判断':<12}{'测验'}")
    print("-" * 82)
    for r in res["rows"]:
        quiz = "—" if not r["quizN"] else f"{r['quizOK']}/{r['quizN']}"
        rate = f"{r['rate']:.1f}" if r["exp"] else "—"
        print(f"{r['ch']:<2}{r['pinyin']:<8}{r['exp']:>4}{r['taps']:>4}{rate:>7}{r['days']:>4}{r['maxSingle']:>4}  {r['judge']:<12}{quiz}")
    print("-" * 82)
    not_seen = [r["ch"] for r in res["rows"] if r["exp"] == 0]
    if not_seen:
        print(f"还没看到（{len(not_seen)}）：{' '.join(not_seen)}")
        print("  这些既不算会、也不算不会，只是还没遇到。")
    weak = [r["ch"] for r in res["rows"] if r["judge"] in ("不会（家长）", "测验未过", "反复点")]
    if weak:
        n = max(1, -(-len(weak) // 5))
        print(f"\n建议下一课：用 {' '.join(weak[:8])} 写一本小书（约 {n} 节预备课的词汇量）")


if __name__ == "__main__":
    main()
