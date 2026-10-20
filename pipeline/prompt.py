"""生成"受字表约束"的写故事提示词。

用法：
    python pipeline/prompt.py --order 4 --new "边 有 树" --pages 3

把输出整段贴给任意 LLM，让它只返回 JSON；再用 lesson.py --from-json 导入。
模型负责想故事，流水线负责保证不超纲——两者分开，模型换了也不影响验收。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, required=True, help="这节课的序号（决定已学字）")
    ap.add_argument("--new", default="", help="本课允许出现的新字")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--chars-per-page", type=int, default=8)
    ap.add_argument("--idea", default="")
    args = ap.parse_args()

    curriculum = common.load_curriculum()
    lessons = common.load_lessons()
    known = common.taught_before(lessons, args.order, curriculum)
    new = common.unique(common.chars(args.new))
    pending = [ch for ch in new if ch not in known]
    pool = [ch for ch in curriculum if ch in known]  # 按字表顺序，读起来像课程进度
    unknown = [ch for ch in new if ch not in curriculum]
    if unknown:
        common.die(f"字表里没有：{' '.join(unknown)}，先补 curriculum.csv")

    pages_json = ",\n".join(
        f'    {{"text": "第{i}页文案。", "visual": "这一页画什么：谁、在哪、做什么、镜头远近；只写画面，不写文字。"}}'
        for i in range(1, args.pages + 1)
    )
    print(f"""你在为一款 3–4 岁孩子的识字 App 写一本 {args.pages} 页的绘本。

【硬约束】
1. 全书只能使用下面这些字：
   已学字：{' '.join(pool)}
   本课新字（可以出现，每个都算"新"）：{' '.join(pending) if pending else '（无，这节课不引入新字）'}
2. 除了上面两行里的字，一个都不许出现。包括人名、语气词、标点以外的符号。
3. 每页 {max(4, args.chars_per_page - 2)}–{args.chars_per_page} 个汉字（标点不计，绝对不超过 {args.chars_per_page + 2}）。
4. 每页只写一件事，画面能画出来：谁、在哪、做什么。
5. 语言口语化，像对 3 岁孩子说话；不用成语，不写拼音，不写"第 X 页"。
6. {args.pages} 页要连成一个完整的小故事：起因 → 发生 → 结果。

【这一本的想法】
{args.idea or '（由你决定，但要适合 3–4 岁）'}

【输出】
只输出一个 JSON，不要解释、不要 Markdown 代码块：
{{
  "title": "四个字以内",
  "world": "一句话说清角色长相和场景，供插画复用",
  "new_chars": ["本课新字，从上面那行里选"],
  "pages": [
{pages_json}
  ]
}}

【交稿前自查】
- 逐字对照"已学字 + 本课新字"，有没有混进别的字？
- 每页汉字数是否在范围内？
- 去掉插图，光读文字能不能看懂？
- 每页的 visual 是否只用了"已学字/新字"能表达的东西？不要引入新角色、新地点。

写完把 JSON 存成 draft.json，然后执行：
python pipeline/lesson.py --id L04 --order {args.order} --from-json draft.json
""")

    total_new = len(pending)
    print(f"（提示：这节课预计引入 {total_new} 个新字；一节字卡课建议不超过 6 个）", file=sys.stderr)


if __name__ == "__main__":
    main()
