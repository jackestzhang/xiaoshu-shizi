"""整页插画流水线：提示词 → 生成/导入 → 转 WebP → 审核。

原则：
  - 一页一张图，图不可点，文字层独立，所以不需要任何热点坐标；
  - 提示词由「全书设定 + 这一页画面 + 固定画风」拼成，画风不靠临场发挥；
  - 生成先落 art/ 源图，审核通过才进 app/，避免半成品混进包里。

用法：
    python pipeline/art.py --id L03 --prompts
    # 手动：按 art/L03/prompts.txt 去即梦/豆包生成，存成 p1.png p2.png p3.png
    python pipeline/art.py --id L03 --import art/L03
    python pipeline/art.py --id L03 --ok

    # 或走 OpenAI 兼容接口（需要 SHIZI_IMG_KEY）
    python pipeline/art.py --id L03 --provider openai
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

# 画风常量：改这一处，全书一起变
STYLE = (
    "儿童绘本插画，面向 3–4 岁：扁平厚涂（gouache）质感，暖色自然光，柔和纸纹，"
    "造型圆润、表情清楚，颜色干净不刺眼；横版构图，主体完整、不切边；"
    "画面中不要出现任何文字、汉字、拼音、数字、水印、边框、页签。"
)

MOOD = {
    "day": "清晨到白天，自然暖光，空气通透",
    "dusk": "黄昏，暖橙晚霞，光线低斜",
    "night": "夜晚，安静月光，深蓝与暖黄对比",
}


def lesson_path(lid: str) -> Path:
    return common.LESSONS / f"{lid}.json"


def load(lid: str) -> dict:
    p = lesson_path(lid)
    if not p.exists():
        common.die(f"没有这节课：{lid}")
    return json.loads(p.read_text(encoding="utf-8"))


def save(d: dict) -> None:
    common.write_json(lesson_path(d["id"]), d)


def make_prompts(lesson: dict) -> list[dict]:
    world = lesson.get("world") or "角色与场景保持统一。"
    out = []
    for i, page in enumerate(lesson.get("pages", []), 1):
        bg = (page.get("scene") or {}).get("bg", "day")
        visual = page.get("visual") or page.get("text", "")
        prompt = (
            f"{STYLE}\n"
            f"【全书设定】{world}\n"
            f"【这一页的画面】{visual}\n"
            f"【情节参考】{page.get('text','')}（只用于理解，不要把这句话画进图里）\n"
            f"【构图】横版 5:3；主体位于画面中下；天空占上方约三分之一；{MOOD.get(bg, MOOD['day'])}。"
        )
        out.append({"page": i, "text": page.get("text", ""), "prompt": prompt})
    return out


def write_prompts(lesson: dict) -> Path:
    d = common.ROOT / "art" / lesson["id"]
    d.mkdir(parents=True, exist_ok=True)
    pages = make_prompts(lesson)
    payload = {"id": lesson["id"], "style": STYLE, "pages": pages}
    (d / "prompts.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# {lesson['id']} {lesson.get('title','')}", "", f"## 画风", STYLE, ""]
    for p in pages:
        lines += [f"## 第 {p['page']} 页", f"文案：{p['text']}", "", p["prompt"], ""]
    lines += [
        "## 使用建议",
        "1. 先生成第 1 页，满意后把它作为参考图生成第 2、3 页（保持角色和画风一致）。",
        "2. 统一 1536×1024 或 5:3 横版；不要在图里留文字。",
        "3. 存成 p1.png / p2.png / p3.png，放进本目录，然后：",
        f"   python pipeline/art.py --id {lesson['id']} --import art/{lesson['id']}",
    ]
    (d / "prompts.txt").write_text("\n".join(lines), encoding="utf-8")
    return d


def provider_openai(lesson: dict, prompts: list[dict], size: str, quality: str) -> None:
    base = (os.getenv("SHIZI_IMG_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("SHIZI_IMG_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("SHIZI_IMG_MODEL") or "gpt-image-1"
    if not key:
        common.die("没有找到 SHIZI_IMG_KEY / OPENAI_API_KEY。也可以先用 --prompts + 手动导入。")

    d = common.ROOT / "art" / lesson["id"]
    d.mkdir(parents=True, exist_ok=True)

    for p in prompts:
        url = f"{base}/images/generations"
        body = json.dumps({"model": model, "prompt": p["prompt"], "size": size, "n": 1, "quality": quality}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            common.die(f"第 {p['page']} 页生成失败：HTTP {e.code} {e.read()[:300]!r}")
        except Exception as e:  # noqa: BLE001
            common.die(f"第 {p['page']} 页生成失败：{e}")

        item = (data.get("data") or [{}])[0]
        raw = None
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as r:
                raw = r.read()
        if not raw:
            common.die(f"第 {p['page']} 页返回里没有图片：{str(data)[:300]}")

        out = d / f"p{p['page']}.png"
        out.write_bytes(raw)
        print(f"  · 第 {p['page']} 页 → {out.relative_to(common.ROOT)}")
        time.sleep(2)

    print(f"\n下一步：python pipeline/art.py --id {lesson['id']} --import {d.relative_to(common.ROOT)}")


def import_images(lesson: dict, src_dir: Path) -> None:
    from PIL import Image, ImageOps

    dst_dir = common.APP / "assets" / "art"
    dst_dir.mkdir(parents=True, exist_ok=True)

    prompts = {p["page"]: p["prompt"] for p in make_prompts(lesson)}
    found = 0
    for i, page in enumerate(lesson.get("pages", []), 1):
        src = None
        for ext in ("png", "jpg", "jpeg", "webp"):
            cand = src_dir / f"p{i}.{ext}"
            if cand.exists():
                src = cand
                break
        if not src:
            common.warn(f"第 {i} 页找不到 p{i}.png/jpg/webp，跳过")
            continue

        img = Image.open(src).convert("RGB")
        img = ImageOps.fit(img, (1280, 768), Image.LANCZOS, centering=(0.5, 0.46))
        out = dst_dir / f"{lesson['id']}_p{i}.webp"
        img.save(out, "WEBP", quality=82, method=6)

        page["art"] = {
            "file": f"assets/art/{out.name}",
            "width": 1280,
            "height": 768,
            "status": "draft",
            "prompt": prompts[i],
            "model": "manual",
            "created": time.strftime("%Y-%m-%d %H:%M"),
        }
        found += 1
        print(f"  · 第 {i} 页 {src.name} → {out.relative_to(common.ROOT)} ({out.stat().st_size/1024:.0f} KB)")

    if not found:
        common.die("一张图都没导入。文件名必须是 p1.png / p2.png …")
    save(lesson)
    print(f"\n✓ 导入 {found} 张，状态 draft。看完没问题：python pipeline/art.py --id {lesson['id']} --ok")


def show(lesson: dict) -> None:
    print(f"{lesson['id']} {lesson.get('title','')} · {len(lesson.get('pages',[]))} 页")
    for i, page in enumerate(lesson.get("pages", []), 1):
        art = page.get("art") or {}
        status = art.get("status", "—")
        f = art.get("file", "（无，使用 SVG 回退）")
        print(f"  第{i}页  {status:<9} {f}  {page.get('text','')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--prompts", action="store_true", help="生成提示词到 art/<ID>/prompts.txt")
    ap.add_argument("--provider", choices=["openai"], help="调用 OpenAI 兼容图片接口")
    ap.add_argument("--size", default="1536x1024")
    ap.add_argument("--quality", default="high")
    ap.add_argument("--import", dest="import_dir", help="从目录导入 p1/p2/... 并转 WebP")
    ap.add_argument("--ok", action="store_true", help="插画审核通过")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    lesson = load(args.id)
    if lesson.get("kind") != "story":
        common.die("只有绘本课需要插画")

    if args.list:
        show(lesson)
        return

    if args.prompts or (not args.provider and not args.import_dir and not args.ok):
        d = write_prompts(lesson)
        print(f"✓ 提示词：{d.relative_to(common.ROOT)}/prompts.txt")
        print(f"  共 {len(make_prompts(lesson))} 页，画风常量在 pipeline/art.py 顶部")
        show(lesson)
        return

    if args.provider:
        prompts = make_prompts(lesson)
        print(f"用 {args.provider} 生成 {len(prompts)} 张（{args.size}）…")
        provider_openai(lesson, prompts, args.size, args.quality)
        return

    if args.import_dir:
        import_images(lesson, Path(args.import_dir))
        return

    if args.ok:
        n = 0
        for page in lesson.get("pages", []):
            if page.get("art"):
                page["art"]["status"] = "approved"
                n += 1
        if not n:
            common.die("还没有导入插画")
        save(lesson)
        common.ok(f"{n} 张插画已确认")
        print(f"下一步：python pipeline/build.py")


if __name__ == "__main__":
    main()
