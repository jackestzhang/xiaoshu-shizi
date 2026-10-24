"""课程校验：字表、页长、拼音、场景、音频。

最关键的一条：故事里出现的每个字，必须已经"教过"（已会字或更早的课），
否则直接判错——而不是先生成再统计缺多少。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import sprites
from common import (
    EXPERIMENTAL_HARD_LIMIT,
    EXPERIMENTAL_PAGE_LIMIT,
    PAGE_HARD_LIMIT,
    PAGE_LIMIT,
    NEW_PER_LESSON,
)


def check_lesson(lesson: dict, lessons: list[dict], curriculum: dict, with_assets: bool) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    lid = lesson.get("id", "?")
    order = lesson.get("order", 999)
    exp = bool(lesson.get("experimental"))
    soft = EXPERIMENTAL_PAGE_LIMIT if exp else PAGE_LIMIT
    hard = EXPERIMENTAL_HARD_LIMIT if exp else PAGE_HARD_LIMIT
    allowed = common.taught_before(lessons, order, curriculum) | set(lesson.get("new_chars") or [])
    if exp:
        notes.append(f"[{lid}] 实验课程：单页最多 {hard} 字，不适合 3–4 岁独立阅读")

    if lesson.get("status") not in ("draft", "confirmed"):
        errors.append(f"[{lid}] status 必须是 draft 或 confirmed")

    if lesson.get("kind") == "cards":
        cards = lesson.get("cards") or []
        if not cards:
            errors.append(f"[{lid}] 字卡课没有字")
        for c in cards:
            ch = c.get("ch")
            if ch not in curriculum:
                errors.append(f"[{lid}] 字 {ch} 不在 curriculum.csv")
            elif not curriculum[ch]["pinyin"] or not curriculum[ch]["word"]:
                errors.append(f"[{lid}] 字 {ch} 缺拼音或配词")
        return errors, notes

    pages = lesson.get("pages") or []
    if not pages:
        errors.append(f"[{lid}] 故事课没有页面")

    for i, page in enumerate(pages, 1):
        text = page.get("text", "")
        cs = common.chars(text)
        if not cs:
            errors.append(f"[{lid}] 第{i}页没有汉字")
            continue
        if len(cs) > hard:
            errors.append(f"[{lid}] 第{i}页 {len(cs)} 字，超过硬上限 {hard}")
        elif len(cs) > soft:
            notes.append(f"[{lid}] 第{i}页 {len(cs)} 字，超过建议上限 {soft}（3–4 岁建议 8–10）")

        out = [ch for ch in cs if ch not in allowed]
        if out:
            errors.append(
                f"[{lid}] 第{i}页超纲字：{' '.join(common.unique(out))}"
                f"（先补字卡课，或在 lesson.py --new 里显式声明）"
            )
        for ch in common.unique(cs):
            if ch not in curriculum:
                errors.append(f"[{lid}] 第{i}页 字 {ch} 不在 curriculum.csv")

        art = page.get("art")
        if art:
            apath = common.APP / art.get("file", "")
            if not apath.exists():
                errors.append(f"[{lid}] 第{i}页插画不存在：{art.get('file')}")
            elif apath.stat().st_size > 900 * 1024:
                notes.append(f"[{lid}] 第{i}页插画 {apath.stat().st_size/1024:.0f} KB，偏大")
            if art.get("status") not in ("draft", "approved"):
                errors.append(f"[{lid}] 第{i}页插画状态必须是 draft 或 approved")
            if not art.get("prompt"):
                notes.append(f"[{lid}] 第{i}页插画缺 prompt，后续不好复现")
            if art.get("stale"):
                notes.append(f"[{lid}] 第{i}页插画可能过期（文案或提示词改过，待重审）")

        scene = page.get("scene") or {}
        if not art and not scene.get("items"):
            errors.append(f"[{lid}] 第{i}页既没有插画，也缺少 scene.items")
        for it in scene.get("items", []):
            if it.get("s") not in sprites.SPRITES:
                errors.append(f"[{lid}] 第{i}页未知精灵 {it.get('s')}")
            for k in ("x", "y"):
                if k in it and not (0 <= it[k] <= 100):
                    errors.append(f"[{lid}] 第{i}页精灵 {it.get('s')} 的 {k} 超出 0–100")

        if with_assets:
            import tts
            if not (common.AUDIO / f"{tts.key_for(text)}.mp3").exists():
                notes.append(f"[{lid}] 第{i}页缺整页语音（运行 build.py）")

    if with_assets:
        import tts
        for ch in common.lesson_chars(lesson):
            if not (common.AUDIO / f"{tts.key_for(ch)}.mp3").exists():
                notes.append(f"[{lid}] 缺单字语音：{ch}")
    return errors, notes


def gap_report(lesson: dict, lessons: list[dict], curriculum: dict, baseline: str) -> None:
    lid = lesson.get("id")
    order = lesson.get("order", 999)
    if baseline == "known":
        base = {ch for ch, v in curriculum.items() if v["status"] == "known"}
        label = "只算已会字（假设不补预备课）"
    else:
        base = common.taught_before(lessons, order, curriculum)
        label = "算上所有更早的课"

    print(f"\n{lid}  {lesson.get('title','')}  词汇预算 · {label}")
    print("=" * 68)
    total_new = []
    for i, page in enumerate(lesson.get("pages", []), 1):
        cs = common.chars(page.get("text", ""))
        new = [ch for ch in common.unique(cs) if ch not in base]
        total_new += new
        print(f"  第{i}页 {len(cs):>2} 字   新字 {len(new)}/{len(common.unique(cs))}   {' '.join(new) if new else '—'}")
    total_new = common.unique(total_new)
    print("-" * 68)
    print(f"  全篇 {sum(len(common.chars(p.get('text',''))) for p in lesson.get('pages', []))} 字，需要 {len(total_new)} 个新字")
    if total_new:
        n = math.ceil(len(total_new) / NEW_PER_LESSON)
        print(f"  按每课 {NEW_PER_LESSON} 字算，要先上约 {n} 节预备课")
        print(f"  候选字：{' '.join(total_new)}")
    else:
        print("  没有超纲字：这本可以现在读。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="校验所有课程（默认）")
    ap.add_argument("--id", help="只校验一节课")
    ap.add_argument("--gap", help="输出某节课的词汇预算")
    ap.add_argument("--baseline", choices=["known", "before"], default="before")
    ap.add_argument("--assets", action="store_true", help="同时检查音频是否齐全")
    args = ap.parse_args()

    curriculum = common.load_curriculum()
    lessons = common.load_lessons()

    if args.gap:
        target = next((l for l in lessons if l["id"] == args.gap), None)
        if not target:
            common.die(f"没有这节课：{args.gap}")
        gap_report(target, lessons, curriculum, args.baseline)
        return

    targets = [l for l in lessons if not args.id or l["id"] == args.id]
    if not targets:
        common.die(f"没有这节课：{args.id}")

    errors, notes = [], []
    print(f"字表 {len(curriculum)} 字 · 课程 {len(lessons)} 节")
    for l in targets:
        e, n = check_lesson(l, lessons, curriculum, args.assets)
        errors += e
        notes += n
        mark = "✗" if e else "✓"
        kind = {"cards": "字卡", "story": "绘本"}.get(l.get("kind"), l.get("kind"))
        if l.get("experimental"):
            kind += "·实验"
        print(f"  {mark} {l['id']}  {kind}  {l.get('title','')}  [{l.get('status')}]  {len(common.lesson_chars(l))} 字")

    for n in notes:
        print(f"  ! {n}")
    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} 个错误", file=sys.stderr)
        sys.exit(1)
    print(f"\n通过（{len(notes)} 条提醒）")


if __name__ == "__main__":
    main()
