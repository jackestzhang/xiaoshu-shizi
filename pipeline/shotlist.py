"""生成分镜单：把每页文案、画面、完整提示词放在一页里，方便外部出图。

用途：当平台图片接口不可用时（或你想用即梦/豆包/本地模型），
打开 shotlist.html 逐页复制提示词，出完图丢回 art/<ID>/，再 --import。

自包含 HTML，零外部请求，预览器里也能打开。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import art  # noqa: E402
import common  # noqa: E402


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#FBF6EC;color:#3B352C;
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  line-height:1.6;-webkit-font-smoothing:antialiased}
header{padding:28px 20px 18px;max-width:1160px;margin:0 auto}
h1{margin:0 0 6px;font-size:24px;letter-spacing:.02em}
.meta{color:#8C7B60;font-size:13px}
.meta b{color:#5F6F55}
.steps{max-width:1160px;margin:0 auto 6px;padding:0 20px}
.steps ol{margin:10px 0 0;padding-left:20px;color:#6C6355;font-size:13px}
.steps code{background:#F0E6D2;border-radius:5px;padding:1px 5px;font-size:12px}
main{max-width:1160px;margin:0 auto;padding:16px 20px 40px;
  display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.card{background:#FFFDF8;border:1px solid #EADFC8;border-radius:16px;padding:16px 16px 14px;
  box-shadow:0 2px 10px rgba(120,95,55,.05);display:flex;flex-direction:column}
.ph{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.n{background:#6F8F6A;color:#FFFDF8;border-radius:9px;font-size:12px;
  padding:2px 9px;font-weight:600;letter-spacing:.06em}
.st{font-size:11px;color:#A99E8B;border:1px dashed #DCCEB2;border-radius:99px;padding:1px 8px}
.st.ok{color:#4F7A4A;border-color:#BBD3B4;background:#F1F7EE}
.label{font-size:11px;color:#A99E8B;letter-spacing:.1em;margin:10px 0 2px}
.text{font-size:17px;margin:0 0 4px;color:#2F2A22;letter-spacing:.04em}
.visual{font-size:13px;color:#6C6355;margin:0}
.prompt{white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.65;
  background:#F7EFDE;border-radius:10px;padding:10px;margin:6px 0 0;
  color:#4A4336;max-height:210px;overflow:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
details summary{cursor:pointer;font-size:12px;color:#6F8F6A;margin-top:10px;user-select:none}
.acts{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
button{border:none;border-radius:10px;padding:8px 14px;font-size:13px;cursor:pointer;
  background:#6F8F6A;color:#FFFDF8;transition:filter .15s}
button:hover{filter:brightness(1.08)}
button.ghost{background:#F0E6D2;color:#6C6355}
button:active{transform:translateY(1px)}
footer{max-width:1160px;margin:0 auto;padding:0 20px 48px;color:#8C7B60;font-size:12px}
footer code{background:#F0E6D2;border-radius:5px;padding:2px 6px;display:inline-block;margin:3px 0}
.toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,10px);background:#3B352C;
  color:#FFF8E8;padding:9px 16px;border-radius:12px;font-size:13px;opacity:0;
  transition:opacity .18s,transform .18s;pointer-events:none;z-index:9}
.toast.on{opacity:1;transform:translate(-50%,0)}
@media (max-width:520px){
  header{padding:20px 14px 12px}h1{font-size:20px}
  main{padding:10px 14px 32px;gap:12px}
  .text{font-size:16px}
}
"""

JS = """
function copyText(s, btn, label) {
  const done = () => {
    const old = btn.textContent;
    btn.textContent = '已复制';
    setTimeout(() => { btn.textContent = old; }, 1200);
    toast(label + '已复制，去出图工具粘贴');
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(s).then(done).catch(() => legacy(s, done));
  } else { legacy(s, done); }
}
function legacy(s, done) {
  const ta = document.createElement('textarea');
  ta.value = s; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); done(); } catch (e) { toast('复制失败，请手动选中'); }
  ta.remove();
}
let tt = null;
function toast(m) {
  const el = document.getElementById('toast');
  el.textContent = m; el.classList.add('on');
  clearTimeout(tt); tt = setTimeout(() => el.classList.remove('on'), 2200);
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-copy]');
  if (!b) return;
  const card = b.closest('.card');
  const kind = b.dataset.copy;
  const src = kind === 'visual' ? card.querySelector('.visual').textContent
            : kind === 'short' ? card.querySelector('.short').textContent
            : card.querySelector('.prompt').textContent;
  copyText(src, b, kind === 'short' ? '精简版提示词' : kind === 'visual' ? '画面描述' : '提示词');
});
"""


SHORT_STYLE = "儿童绘本插画，扁平厚涂，暖色自然光，纸纹质感，圆润造型，颜色干净；"


def short_prompt(page: dict) -> str:
    """精简版：给对长提示词不敏感的工具用。"""
    visual = (page.get("visual") or page.get("text", "")).strip()
    return f"{SHORT_STYLE}{visual} 横版构图，主体完整不切边；画面中不要出现任何文字、拼音、数字、水印。"


def page_card(n: int, page: dict, prompt: str, exists: bool) -> str:
    esc = html.escape
    status = '<span class="st ok">图已导入</span>' if exists else '<span class="st">待出图</span>'
    return f"""    <article class="card" data-n="{n}">
      <div class="ph"><span class="n">{n:02d}</span>{status}</div>
      <div class="label">文案</div>
      <p class="text">{esc(page.get('text', ''))}</p>
      <div class="label">画面</div>
      <p class="visual">{esc(page.get('visual', ''))}</p>
      <details>
        <summary>完整提示词（点开）</summary>
        <pre class="prompt">{esc(prompt)}</pre>
      </details>
      <pre class="short" hidden>{esc(short_prompt(page))}</pre>
      <div class="acts">
        <button data-copy="prompt">复制提示词</button>
        <button class="ghost" data-copy="short">精简版</button>
        <button class="ghost" data-copy="visual">只复制画面</button>
      </div>
    </article>"""


def build(lesson_id: str) -> Path:
    lesson = next((l for l in common.load_lessons() if l["id"] == lesson_id), None)
    if not lesson:
        common.die(f"找不到课程：{lesson_id}")

    prompts = {p["page"]: p["prompt"] for p in art.make_prompts(lesson)}
    pages = art.pages(lesson)
    cards = []
    done = 0
    for i, page in enumerate(pages, 1):
        exists = bool((page.get("art") or {}).get("file"))
        done += 1 if exists else 0
        cards.append(page_card(i, page, prompts[i], exists))

    out = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>分镜单 · {html.escape(lesson.get('title', lesson_id))}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html.escape(lesson.get('title', lesson_id))}</h1>
  <div class="meta">{len(pages)} 页 · 已导入 <b>{done}</b>/{len(pages)} · 比例 5:3（出图选 16:9 或 3:2，会自动裁切）</div>
</header>
<div class="steps">
  <ol>
    <li>点每页的「复制提示词」，粘到即梦 / 豆包 / 你常用的图片模型。</li>
    <li>下载图片，命名 <code>p1.png</code> … <code>p{len(pages)}.png</code>；不命名也行，按修改时间顺序对应页码。</li>
    <li>全部丢进 <code>art/{lesson_id}/</code>，然后运行下面的导入命令。</li>
  </ol>
</div>
<main>
{chr(10).join(cards)}
</main>
<footer>
  <div class="label">导入与审核</div>
  <code>python3 pipeline/art.py --id {lesson_id} --import art/{lesson_id}</code><br>
  <code>python3 pipeline/art.py --id {lesson_id} --ok</code><br>
  <code>python3 pipeline/build.py &amp;&amp; python3 pipeline/bundle.py</code>
</footer>
<div class="toast" id="toast"></div>
<script>{JS}</script>
</body>
</html>
"""
    dest = art.art_dir(lesson) / "shotlist.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="生成分镜单 HTML")
    ap.add_argument("--id", required=True, help="课程 ID，例如 L04")
    args = ap.parse_args()
    p = build(args.id)
    print(f"✓ 分镜单：{p.relative_to(common.ROOT)}")
