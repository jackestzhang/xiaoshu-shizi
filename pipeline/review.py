"""文案确认：生成审阅页 / 改一页 / 确认后解锁打包。

这是流水线里的硬闸门：status=draft 的课，build.py 不出语音、不出图。
理由是成本——改一句话几乎免费，做错一页语音和插画要重来。
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import scene as scene_mod


def page_html(lesson: dict, page: dict, idx: int, allowed: set[str], curriculum: dict) -> str:
    text = page.get("text", "")
    cs = common.chars(text)
    new = [ch for ch in common.unique(cs) if ch not in allowed]
    chips = "".join(
        f'<span class="chip">{html.escape(ch)}<i>{html.escape(curriculum[ch]["pinyin"])}</i></span>'
        for ch in common.unique(cs)
    )
    art = page.get("art") or {}
    if art.get("file"):
        visual = f'<img class="art" src="../app/{html.escape(art["file"])}" alt="">'
        art_badge = f'插画 {art.get("status","?")}'
    else:
        visual = f'<div class="scene" data-scene=\'{html.escape(json.dumps(page.get("scene") or {}, ensure_ascii=False))}\'></div>'
        art_badge = "插画：SVG 回退"
    return f"""
    <section class="page">
      <div class="phead"><span>第 {idx} 页</span><span>{len(cs)} 字 · 新字 {len(new)} · {art_badge}</span></div>
      {visual}
      <div class="text">{html.escape(text)}</div>
      <div class="chips">{chips}</div>
      {"<div class='warn'>新字：" + " ".join(new) + "</div>" if new else ""}
    </section>"""


def render(lesson: dict, lessons: list[dict], curriculum: dict) -> Path:
    allowed = common.taught_before(lessons, lesson["order"], curriculum)
    pages = "".join(page_html(lesson, p, i, allowed, curriculum) for i, p in enumerate(lesson.get("pages", []), 1))
    total = sum(len(common.chars(p.get("text", ""))) for p in lesson.get("pages", []))
    status = lesson.get("status", "draft")
    badge = "已确认" if status == "confirmed" else "草稿 · 未确认"
    cmd_ok = f"python pipeline/review.py --id {lesson['id']} --ok --build"

    doc = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文案确认 · {html.escape(lesson['title'])}</title>
<style>
  :root{{--paper:#FBF6EC;--ink:#3B352C;--sage:#6F8F6A;--ochre:#C98A44;--line:#E7DCC6}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.7 -apple-system,"PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;padding:32px 20px 80px}}
  .wrap{{max-width:860px;margin:0 auto}}
  h1{{font-size:26px;margin:0 0 6px}}
  .meta{{color:#8A8172;font-size:13px;margin-bottom:6px}}
  .badge{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;background:{'#E7F0E4' if status=='confirmed' else '#FBEBDA'};color:{'#4F7049' if status=='confirmed' else '#B4712F'}}}
  .world{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:18px 0;font-size:13px;color:#6E6557}}
  .page{{background:#fff;border:1px solid var(--line);border-radius:20px;padding:14px;margin:18px 0;box-shadow:0 6px 18px rgba(90,70,40,.05)}}
  .phead{{display:flex;justify-content:space-between;font-size:12px;color:#9A9182;margin-bottom:8px}}
  .scene{{border-radius:12px;overflow:hidden;background:#F5E9D5}}
  .scene svg,.art{{display:block;width:100%;height:auto;border-radius:12px}}
  .text{{font-size:30px;letter-spacing:.08em;margin:14px 4px 8px}}
  .chips{{display:flex;flex-wrap:wrap;gap:8px}}
  .chip{{display:inline-flex;flex-direction:column;align-items:center;background:#FBF6EC;border:1px solid var(--line);border-radius:10px;padding:6px 10px;font-size:22px;line-height:1.1}}
  .chip i{{font-style:normal;font-size:11px;color:#8A8172;margin-top:3px}}
  .warn{{margin-top:8px;font-size:13px;color:#B4712F}}
  code{{background:#F3EAD8;padding:2px 6px;border-radius:5px;font-size:13px}}
  .foot{{position:fixed;left:0;right:0;bottom:0;background:rgba(251,246,236,.95);border-top:1px solid var(--line);padding:12px 20px;text-align:center;font-size:13px}}
  .hint{{color:#8A8172}}
</style>
<body><div class="wrap">
  <h1>{html.escape(lesson['title'])}</h1>
  <div class="meta">{lesson['id']} · {len(lesson.get('pages',[]))} 页 · {total} 字 · <span class="badge">{badge}</span></div>
  <div class="world"><b>全书设定</b><br>{html.escape(lesson.get('world') or '（未填）')}</div>
  {pages}
  <p class="hint">改文案：<code>python pipeline/review.py --id {lesson['id']} --text 2 "新的第二页"</code><br>
  改完会自动打回草稿。确认并打包：<code>{cmd_ok}</code><br>
  插画确认：<code>python pipeline/art.py --id {lesson['id']} --ok</code>
  · 生成提示词：<code>python pipeline/art.py --id {lesson['id']} --prompts</code></p>
</div>
<div class="foot">审阅页只读 · 确认动作在命令行（保证状态可追溯）</div>
<script src="../app/sprites.js"></script>
<script src="../app/scene.js"></script>
<script>
  document.querySelectorAll('.scene').forEach(el => {{
    const scene = JSON.parse(el.dataset.scene || '{{}}');
    el.innerHTML = window.renderScene(scene, {{spots:false, animate:false}});
  }});
</script>
</body></html>"""
    out = common.REVIEW / f"review-{lesson['id']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--ok", action="store_true", help="确认文案")
    ap.add_argument("--text", nargs=2, metavar=("PAGE", "TEXT"), help="改第 N 页文案")
    ap.add_argument("--build", action="store_true", help="确认后顺手打包")
    args = ap.parse_args()

    curriculum = common.load_curriculum()
    lessons = common.load_lessons()
    lesson = next((l for l in lessons if l["id"] == args.id), None)
    if not lesson:
        common.die(f"没有这节课：{args.id}")
    if lesson.get("kind") != "story":
        common.die("字卡课没有文案可确认")

    if args.text:
        idx = int(args.text[0])
        if not (1 <= idx <= len(lesson["pages"])):
            common.die(f"页码超出范围：{idx}")
        lesson["pages"][idx - 1]["text"] = args.text[1]
        lesson["pages"][idx - 1]["scene"] = scene_mod.auto_scene(args.text[1], idx)
        lesson["status"] = "draft"
        common.write_json(Path(lesson["_path"]), {k: v for k, v in lesson.items() if not k.startswith("_")})
        common.ok(f"第 {idx} 页已改，状态打回 draft（旧语音因内容哈希自动失效）")

    if args.ok:
        lesson["status"] = "confirmed"
        common.write_json(Path(lesson["_path"]), {k: v for k, v in lesson.items() if not k.startswith("_")})
        common.ok(f"{args.id} 文案已确认")

    out = render(lesson, lessons, curriculum)
    print(f"审阅页：{out.relative_to(common.ROOT)}")
    if lesson.get("status") != "confirmed":
        print("下一步：看完没问题后执行  python pipeline/review.py --id {} --ok --build".format(args.id))
    elif args.build:
        import subprocess
        subprocess.run([sys.executable, str(common.ROOT / "pipeline" / "build.py")], check=True)


if __name__ == "__main__":
    main()
