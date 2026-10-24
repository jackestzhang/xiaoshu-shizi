"""公共工具：字表、课程、汉字切分、拼音。"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LESSONS = DATA / "lessons"
APP = ROOT / "app"
AUDIO = APP / "assets" / "audio"
REVIEW = ROOT / "review"
ARCHIVE = ROOT / "archive"

HANZI = re.compile(r"[\u4e00-\u9fff]")

PAGE_LIMIT = 10        # 3–4 岁单页建议上限（汉字，不含标点）
PAGE_HARD_LIMIT = 12   # 超过直接判错
NEW_PER_LESSON = 6     # 一节预备课大约几个新字（用于估算）

# 实验模式：只用于流程压力测试，不适合 3–4 岁独立阅读
EXPERIMENTAL_PAGE_LIMIT = 20
EXPERIMENTAL_HARD_LIMIT = 22


def chars(text: str) -> list[str]:
    return HANZI.findall(text or "")


def unique(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def load_curriculum() -> dict[str, dict]:
    path = DATA / "curriculum.csv"
    rows = {}
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ch = (r.get("char") or "").strip()
            if not ch:
                continue
            rows[ch] = {
                "char": ch,
                "pinyin": (r.get("pinyin") or "").strip(),
                "word": (r.get("word") or "").strip(),
                "status": (r.get("status") or "planned").strip(),
                "lesson": (r.get("lesson") or "").strip(),
            }
    return rows


def load_lessons() -> list[dict]:
    items = []
    for p in sorted(LESSONS.glob("*.json")):
        with p.open(encoding="utf-8") as f:
            d = json.load(f)
        d["_path"] = str(p)
        items.append(d)
    items.sort(key=lambda x: (x.get("order", 999), x.get("id", "")))
    return items


def lesson_chars(lesson: dict) -> list[str]:
    if lesson.get("kind") == "cards":
        return unique([c["ch"] for c in lesson.get("cards", [])])
    out = []
    for page in lesson.get("pages", []):
        out += chars(page.get("text", ""))
    return unique(out)


def taught_before(lessons: list[dict], order: int, curriculum: dict) -> set[str]:
    """基准集合：已会字 + 排在当前课之前的所有课的字。"""
    known = {ch for ch, v in curriculum.items() if v["status"] == "known"}
    for l in lessons:
        if l.get("order", 999) < order:
            known |= set(lesson_chars(l))
    return known


def pinyin_of(ch: str, curriculum: dict) -> str:
    return curriculum.get(ch, {}).get("pinyin", "")


def word_of(ch: str, curriculum: dict) -> str:
    return curriculum.get(ch, {}).get("word", "")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def die(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def warn(msg: str) -> None:
    print(f"! {msg}")
