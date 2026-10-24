"""新建 / 重生成课程草稿。

约束生成是这里的核心：故事用字必须落在"已会 + 更早的课 + 本课显式新字"里。
不满足就不写文件，并告诉你差哪些字、要补几节预备课。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import scene as scene_mod
from common import PAGE_HARD_LIMIT, PAGE_LIMIT


def build_story(args, curriculum, lessons) -> dict:
    pages_text = [p.strip() for p in args.pages.split("|") if p.strip()]
    if not pages_text:
        common.die("--pages 为空，用 | 分隔每一页")

    allowed = common.taught_before(lessons, args.order, curriculum) | set(args.new)
    soft = args.page_limit or PAGE_LIMIT
    hard = args.page_limit or PAGE_HARD_LIMIT
    problems, warnings = [], []
    out_all, missing_all = set(), set()
    pages = []
    for i, text in enumerate(pages_text, 1):
        cs = common.chars(text)
        if not cs:
            problems.append(f"第{i}页没有汉字")
            continue
        if len(cs) > hard:
            problems.append(f"第{i}页 {len(cs)} 字，超过硬上限 {hard}")
        elif len(cs) > soft:
            warnings.append(f"第{i}页 {len(cs)} 字，超过建议上限 {soft}")

        out = [ch for ch in common.unique(cs) if ch not in allowed]
        if out:
            out_all |= set(out)
            problems.append(f"第{i}页超纲字：{' '.join(out)}")
        missing = [ch for ch in common.unique(cs) if ch not in curriculum]
        if missing:
            missing_all |= set(missing)
            problems.append(f"第{i}页字表里没有：{' '.join(missing)}")

        sc = {"bg": "day", "items": []} if args.no_scene else scene_mod.auto_scene(text, i)
        pages.append({"text": text, "scene": sc})

    for i, v in enumerate(getattr(args, "visuals", []) or []):
        if i < len(pages) and v:
            pages[i]["visual"] = v

    new_chars = common.unique([ch for p in pages for ch in common.chars(p["text"]) if ch not in common.taught_before(lessons, args.order, curriculum)])
    declared = set(args.new)
    undeclared = [ch for ch in new_chars if ch not in declared]
    if undeclared:
        problems.append(f"这些字是本课新字，但没有用 --new 声明：{' '.join(undeclared)}")

    for w in warnings:
        common.warn(w)
    if problems:
        print("\n没有写文件。问题：", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        if missing_all:
            print(f"\n先补字表：把 {' '.join(sorted(missing_all))} 加进 data/curriculum.csv（拼音要人工核过）", file=sys.stderr)
        pending = [ch for ch in common.unique(undeclared) if ch not in missing_all]
        if pending:
            n = max(1, -(-len(pending) // 6))
            print(f"\n两种改法：", file=sys.stderr)
            print(f"  1) 把 {' '.join(pending)} 放进 {n} 节字卡课，再回来写故事；", file=sys.stderr)
            print(f"  2) 如果只是试写，加 --new {' '.join(pending)}（会记成'本课新字'）", file=sys.stderr)
        sys.exit(1)
    if warnings and args.strict:
        common.die("有页面超过建议上限（--strict）")

    return {
        "id": args.id,
        "order": args.order,
        "kind": "story",
        "title": args.title,
        "status": "draft",
        "world": args.world,
        "new_chars": args.new,
        **({"page_limit": args.page_limit} if args.page_limit else {}),
        "pages": pages,
    }


def build_cards(args, curriculum, lessons) -> dict:
    cs = common.unique(common.chars(args.chars))
    if not cs:
        common.die("--chars 里没有汉字")
    missing = [ch for ch in cs if ch not in curriculum]
    if missing:
        common.die(f"字表里没有：{' '.join(missing)}，先补 data/curriculum.csv")
    return {
        "id": args.id,
        "order": args.order,
        "kind": "cards",
        "title": args.title,
        "status": "draft",
        "cards": [{"ch": ch} for ch in cs],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--order", type=int, default=None)
    ap.add_argument("--kind", choices=["story", "cards"], default="story")
    ap.add_argument("--title", default="")
    ap.add_argument("--pages", help="绘本文案，用 | 分页")
    ap.add_argument("--from-json", help="从 LLM 返回的 JSON 导入（title/world/new_chars/pages）")
    ap.add_argument("--chars", help="字卡课的字，例如 兔树跑来")
    ap.add_argument("--new", default="", help="本课允许出现的新字")
    ap.add_argument("--world", default="", help="全书共用设定（角色/场景）")
    ap.add_argument("--regen", action="store_true", help="归档旧版后重生成")
    ap.add_argument("--strict", action="store_true", help="超过建议页长直接失败")
    ap.add_argument("--no-scene", action="store_true", help="不自动生成场景")
    ap.add_argument("--page-limit", type=int, metavar="N",
                    help="本课单页汉字上限（默认 10，硬上限 12）；长故事可设 20")
    args = ap.parse_args()

    if args.from_json:
        src = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        src_pages = src.get("pages", [])
        args.pages = "|".join(p.get("text", "") for p in src_pages)
        args.visuals = [p.get("visual", "") for p in src_pages]
        args.title = args.title or src.get("title", "")
        args.world = args.world or src.get("world", "")
        if not args.new and src.get("new_chars"):
            args.new = "".join(src["new_chars"])

    args.new = common.unique(common.chars(args.new))
    curriculum = common.load_curriculum()
    lessons = common.load_lessons()
    existing = next((l for l in lessons if l["id"] == args.id), None)

    if existing and not args.regen:
        common.die(f"{args.id} 已存在。要覆盖请加 --regen（旧版会先归档）")
    args.order = args.order if args.order is not None else (existing or {}).get("order", len(lessons) + 1)
    args.title = args.title or (existing or {}).get("title", args.id)

    # 先在内存里生成，全部通过之后才动旧文件——避免"归档成功、生成失败"
    if args.kind == "story":
        if not args.pages:
            common.die("故事课需要 --pages")
        lesson = build_story(args, curriculum, lessons)
    else:
        if not args.chars:
            common.die("字卡课需要 --chars")
        lesson = build_cards(args, curriculum, lessons)

    old = common.LESSONS / f"{args.id}.json"
    if old.exists() and args.regen:
        dest = common.ARCHIVE / f"{args.id}-{common.stamp()}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, dest / f"{args.id}.json")
        common.ok(f"旧版已归档到 {dest.relative_to(common.ROOT)}")

    common.write_json(old, lesson)
    n = len(common.lesson_chars(lesson))
    print(f"\n✓ {args.id}  {lesson['title']}  已写入（status=draft）")
    if lesson["kind"] == "story":
        print(f"  {len(lesson['pages'])} 页 · {n} 个不同的字 · 本课新字 {len(args.new) or 0}")
    else:
        print(f"  字卡 {n} 张")
    print(f"  下一步：python pipeline/review.py --id {args.id}   （看文案，确认后才出语音）")


if __name__ == "__main__":
    main()
