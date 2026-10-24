"""整页插画流水线：提示词 → 生成/导入 → 转 WebP → 逐页审核。

原则：
  - 一页一张图，图不可点，文字层独立，所以不需要任何热点坐标；
  - 提示词 = 固定画风 + 全书设定 + 这一页画面，画风不靠临场发挥；
  - 源图先落 art/<ID>/，审核通过才进 app/，避免半成品混进包里；
  - 每次替换/重生成，旧图自动备份到 art/<ID>/versions/。

常用：
    python pipeline/art.py --id L03 --list
    python pipeline/art.py --id L03 --prompts
    python pipeline/art.py --id L03 --import art/L03
    python pipeline/art.py --id L03 --ok

逐页：
    python pipeline/art.py --id L03 --prompt 2 "小兔从左边跑来，撞上树桩"
    python pipeline/art.py --id L03 --prompt 2 "完整提示词……" --full
    python pipeline/art.py --id L03 --regen 2          # 需要 SHIZI_IMG_KEY
    python pipeline/art.py --id L03 --replace 2 my.png # 直接用自己的图
    python pipeline/art.py --id L03 --ok 2             # 只通过第 2 页
    python pipeline/art.py --id L03 --versions 2
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
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

EXTS = (".png", ".jpg", ".jpeg", ".webp")


# ---------------- 课程读写 ----------------

def lesson_path(lid: str) -> Path:
    return common.LESSONS / f"{lid}.json"


def load(lid: str) -> dict:
    p = lesson_path(lid)
    if not p.exists():
        common.die(f"没有这节课：{lid}")
    return json.loads(p.read_text(encoding="utf-8"))


def save(d: dict) -> None:
    common.write_json(lesson_path(d["id"]), d)


def art_dir(lesson: dict) -> Path:
    return common.ROOT / "art" / lesson["id"]


def pages(lesson: dict) -> list[dict]:
    return lesson.get("pages", [])


def get_page(lesson: dict, n: int) -> dict:
    ps = pages(lesson)
    if not 1 <= n <= len(ps):
        common.die(f"页码超出范围：{n}（共 {len(ps)} 页）")
    return ps[n - 1]


# ---------------- 提示词 ----------------

def build_prompt(lesson: dict, page: dict) -> str:
    """完整自定义优先；否则由 画风 + 设定 + 画面 + 构图 拼成。"""
    if page.get("art_prompt"):
        return page["art_prompt"]
    world = lesson.get("world") or "角色与场景保持统一。"
    bg = (page.get("scene") or {}).get("bg", "day")
    visual = page.get("visual") or page.get("text", "")
    return (
        f"{STYLE}\n"
        f"【全书设定】{world}\n"
        f"【这一页的画面】{visual}\n"
        f"【情节参考】{page.get('text','')}（只用于理解，不要把这句话画进图里）\n"
        f"【构图】横版 5:3；主体位于画面中下；天空占上方约三分之一；{MOOD.get(bg, MOOD['day'])}。"
    )


def make_prompts(lesson: dict) -> list[dict]:
    out = []
    for i, page in enumerate(pages(lesson), 1):
        out.append({
            "page": i,
            "text": page.get("text", ""),
            "prompt": build_prompt(lesson, page),
            "mode": "full" if page.get("art_prompt") else "generated",
        })
    return out


def write_prompts(lesson: dict) -> Path:
    d = art_dir(lesson)
    d.mkdir(parents=True, exist_ok=True)
    ps = make_prompts(lesson)
    payload = {"id": lesson["id"], "style": STYLE, "pages": ps}
    (d / "prompts.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# {lesson['id']} {lesson.get('title','')}", "", "## 画风", STYLE, ""]
    for p in ps:
        tag = "完整自定义" if p["mode"] == "full" else "自动拼接"
        lines += [f"## 第 {p['page']} 页（{tag}）", f"文案：{p['text']}", "", p["prompt"], ""]
    lines += [
        "## 逐页操作",
        f"  python pipeline/art.py --id {lesson['id']} --prompt 2 \"新的画面描述\"",
        f"  python pipeline/art.py --id {lesson['id']} --prompt 2 \"完整提示词\" --full",
        f"  python pipeline/art.py --id {lesson['id']} --regen 2",
        f"  python pipeline/art.py --id {lesson['id']} --replace 2 my.png",
        f"  python pipeline/art.py --id {lesson['id']} --ok 2",
    ]
    (d / "prompts.txt").write_text("\n".join(lines), encoding="utf-8")

    # 每页一个纯文本：直接全选复制，粘到即梦/豆包，不用从长文件里挑
    for p in ps:
        (d / f"p{p['page']}.txt").write_text(p["prompt"], encoding="utf-8")
    return d


def set_prompt(lesson: dict, n: int, text: str, full: bool) -> None:
    page = get_page(lesson, n)
    if full:
        page["art_prompt"] = text
    else:
        page["visual"] = text
        if page.pop("art_prompt", None):
            common.warn(f"第 {n} 页原来的完整自定义提示词已清除")
    if page.get("art"):
        page["art"]["status"] = "draft"
        page["art"]["stale"] = True
        page["art"]["prompt"] = build_prompt(lesson, page)
    save(lesson)
    mode = "完整提示词" if full else "画面描述"
    common.ok(f"第 {n} 页{mode}已更新" + ("（原图标记为待重审）" if page.get("art") else ""))


# ---------------- 源图与版本 ----------------

def find_source(d: Path, n: int) -> Path | None:
    for ext in EXTS:
        p = d / f"p{n}{ext}"
        if p.exists():
            return p
    return None


def backup_source(d: Path, n: int) -> Path | None:
    src = find_source(d, n)
    if not src:
        return None
    vdir = d / "versions"
    vdir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = vdir / f"p{n}_{stamp}{src.suffix}"
    i = 2
    while dest.exists():
        dest = vdir / f"p{n}_{stamp}-{i}{src.suffix}"
        i += 1
    shutil.copy2(src, dest)
    return dest


def clear_sources(d: Path, n: int, keep: Path | None = None) -> None:
    for ext in EXTS:
        p = d / f"p{n}{ext}"
        if p.exists() and (keep is None or p.resolve() != keep.resolve()):
            p.unlink()


def apply_image(lesson: dict, n: int, src: Path, prompt: str, model: str, source: str) -> Path:
    """把任意尺寸的源图裁成 5:3 WebP，并写回课程。"""
    from PIL import Image, ImageOps

    dst_dir = common.APP / "assets" / "art"
    dst_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    img = ImageOps.fit(img, (1280, 768), Image.LANCZOS, centering=(0.5, 0.46))
    out = dst_dir / f"{lesson['id']}_p{n}.webp"
    img.save(out, "WEBP", quality=82, method=6)

    page = get_page(lesson, n)
    page["art"] = {
        "file": f"assets/art/{out.name}",
        "width": 1280,
        "height": 768,
        "status": "draft",
        "stale": False,
        "prompt": prompt,
        "model": model,
        "source": source,
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    return out


def stage_source(lesson: dict, n: int, src: Path) -> Path:
    """把源图复制到 art/<ID>/pN.ext，先备份旧图，再清掉同页其他后缀。"""
    d = art_dir(lesson)
    d.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix not in EXTS:
        common.die(f"只支持 {' / '.join(EXTS)}；HEIC 请先转成 JPG")
    backup_source(d, n)
    dest = d / f"p{n}{suffix}"
    clear_sources(d, n, keep=dest)
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def import_images(lesson: dict, src_dir: Path) -> None:
    prompts = {p["page"]: p["prompt"] for p in make_prompts(lesson)}
    n_pages = len(pages(lesson))

    # 命名优先；命名不全时，退化为“目录里的图按修改时间排序，第几个就是第几页”
    # 这样从即梦/豆包下载的一串乱名也能直接丢进来
    named = {}
    for i in range(1, n_pages + 1):
        for ext in EXTS:
            cand = src_dir / f"p{i}{ext}"
            if cand.exists():
                named[i] = cand
                break

    fallback = []
    if len(named) < n_pages:
        used = set(named.values())
        fallback = sorted(
            (f for f in src_dir.iterdir()
             if f.is_file() and f.suffix.lower() in EXTS and f not in used),
            key=lambda f: (f.stat().st_mtime, f.name),
        )
        if fallback:
            print(f"  没找到完整 p1..p{n_pages} 命名，按修改时间取目录里前 {min(len(fallback), n_pages)} 张")

    found = 0
    for i in range(1, n_pages + 1):
        src = named.get(i)
        if not src and fallback:
            src = fallback[i - 1] if i - 1 < len(fallback) else None
        if not src:
            common.warn(f"第 {i} 页找不到图，跳过")
            continue
        print(f"  第 {i} 页 ← {src.name}")
        staged = stage_source(lesson, i, src)
        out = apply_image(lesson, i, staged, prompts[i], "manual", "import")
        found += 1
        print(f"  · 第 {i} 页 {src.name} → {out.relative_to(common.ROOT)} ({out.stat().st_size/1024:.0f} KB)")

    if not found:
        common.die(
            "一张图都没导入。\n"
            f"  把图片放进 {src_dir}，命名成 p1.png … p{n_pages}.png；\n"
            "  或者直接丢进去，按修改时间顺序对应页码。"
        )
    save(lesson)
    print(f"\n✓ 导入 {found} 张，状态 draft。逐页通过：--ok 2；全部通过：--ok")


def replace_page(lesson: dict, n: int, src: Path) -> None:
    if not src.exists():
        common.die(f"文件不存在：{src}")
    get_page(lesson, n)
    staged = stage_source(lesson, n, src)
    prompt = build_prompt(lesson, get_page(lesson, n))
    out = apply_image(lesson, n, staged, prompt, "manual", "user")
    save(lesson)
    common.ok(f"第 {n} 页已替换为 {src.name} → {out.relative_to(common.ROOT)}")
    print(f"  下一步：python pipeline/art.py --id {lesson['id']} --ok {n}")


# ---------------- API 生成 ----------------

def api_config() -> tuple[str, str, str]:
    base = (os.getenv("SHIZI_IMG_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("SHIZI_IMG_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("SHIZI_IMG_MODEL") or "gpt-image-1"
    if not key:
        common.die(
            "没有找到 SHIZI_IMG_KEY / OPENAI_API_KEY。\n"
            "  也可以先 --prompts，用即梦/豆包生成后 --replace N 文件。"
        )
    return base, key, model


def api_generate(prompt: str, size: str, quality: str) -> bytes:
    base, key, model = api_config()
    body = json.dumps({"model": model, "prompt": prompt, "size": size, "n": 1, "quality": quality}).encode()
    req = urllib.request.Request(
        f"{base}/images/generations", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        common.die(f"生成失败：HTTP {e.code} {e.read()[:300]!r}")
    except Exception as e:  # noqa: BLE001
        common.die(f"生成失败：{e}")

    item = (data.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=120) as r:
            return r.read()
    common.die(f"返回里没有图片：{str(data)[:300]}")


def generate_pages(lesson: dict, nums: list[int], size: str, quality: str) -> None:
    d = art_dir(lesson)
    d.mkdir(parents=True, exist_ok=True)
    for n in nums:
        page = get_page(lesson, n)
        prompt = build_prompt(lesson, page)
        print(f"  · 第 {n} 页生成中（{size}）…", flush=True)
        raw = api_generate(prompt, size, quality)

        backup_source(d, n)
        out_src = d / f"p{n}.png"
        clear_sources(d, n, keep=out_src)
        out_src.write_bytes(raw)

        out = apply_image(lesson, n, out_src, prompt, os.getenv("SHIZI_IMG_MODEL") or "gpt-image-1", "api")
        print(f"    第 {n} 页 → {out.relative_to(common.ROOT)} ({out.stat().st_size/1024:.0f} KB)")
        time.sleep(2)

    save(lesson)
    print(f"\n✓ 完成 {len(nums)} 页，状态 draft。逐页看：--ok N；全部通过：--ok")


# ---------------- 审核与查看 ----------------

def approve(lesson: dict, target: str) -> None:
    if target == "all":
        targets = list(range(1, len(pages(lesson)) + 1))
    else:
        try:
            targets = [int(target)]
        except ValueError:
            common.die(f"页码必须是数字或省略：--ok 2")
        get_page(lesson, targets[0])

    n_ok, missing = 0, []
    for n in targets:
        page = get_page(lesson, n)
        if not page.get("art"):
            missing.append(n)
            continue
        page["art"]["status"] = "approved"
        page["art"]["stale"] = False
        n_ok += 1

    if not n_ok:
        common.die("这些页还没有插画，无法通过")
    save(lesson)
    common.ok(f"{n_ok} 页插画已通过" + (f"（第 {'、'.join(map(str, missing))} 页没有插画）" if missing else ""))
    print("  下一步：python pipeline/build.py")


def show(lesson: dict) -> None:
    d = art_dir(lesson)
    print(f"{lesson['id']} {lesson.get('title','')} · {len(pages(lesson))} 页")
    for i, page in enumerate(pages(lesson), 1):
        art = page.get("art") or {}
        status = art.get("status", "—")
        if art.get("stale"):
            status += "/stale"
        src = art.get("source", "—")
        mode = "full" if page.get("art_prompt") else "auto"
        f = art.get("file", "（无，SVG 回退）")
        versions = len(list((d / "versions").glob(f"p{i}_*"))) if (d / "versions").exists() else 0
        print(f"  第{i}页  {status:<12} {src:<7} prompt:{mode:<4} v{versions:<2} {f}")
        print(f"         文案：{page.get('text','')}")


def list_versions(lesson: dict, n: int) -> None:
    get_page(lesson, n)
    d = art_dir(lesson) / "versions"
    files = sorted(d.glob(f"p{n}_*")) if d.exists() else []
    if not files:
        print(f"第 {n} 页没有历史版本")
        return
    print(f"第 {n} 页历史版本（{len(files)}）：")
    for f in files:
        print(f"  {f.relative_to(common.ROOT)}  {f.stat().st_size/1024:.0f} KB")


# ---------------- CLI ----------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--prompts", action="store_true", help="重写 art/<ID>/prompts.txt")

    ap.add_argument("--prompt", nargs=2, action="append", metavar=("PAGE", "TEXT"),
                    help="改某页的画面描述；配合 --full 可写完整提示词")
    ap.add_argument("--full", action="store_true", help="--prompt 写的是完整提示词，不再拼接画风/设定")

    ap.add_argument("--import", dest="import_dir", help="从目录批量导入 p1/p2/…")
    ap.add_argument("--replace", nargs=2, metavar=("PAGE", "FILE"), help="用自己的图替换某页")
    ap.add_argument("--regen", type=int, metavar="PAGE", help="只重生成某页（需要图片接口）")
    ap.add_argument("--provider", choices=["openai"], help="批量调用 OpenAI 兼容接口")
    ap.add_argument("--size", default="1536x1024")
    ap.add_argument("--quality", default="high")

    ap.add_argument("--ok", nargs="?", const="all", metavar="PAGE",
                    help="通过某页；不带页码则全部通过")
    ap.add_argument("--versions", type=int, metavar="PAGE", help="列出某页历史版本")
    args = ap.parse_args()

    lesson = load(args.id)
    if lesson.get("kind") != "story":
        common.die("只有绘本课需要插画")

    if args.list:
        show(lesson)
        return
    if args.versions:
        list_versions(lesson, args.versions)
        return

    did = False

    if args.prompt:
        for page_s, text in args.prompt:
            set_prompt(lesson, int(page_s), text, args.full)
        did = True

    if args.replace:
        replace_page(lesson, int(args.replace[0]), Path(args.replace[1]))
        did = True

    if args.regen:
        generate_pages(lesson, [args.regen], args.size, args.quality)
        did = True
    elif args.provider:
        generate_pages(lesson, list(range(1, len(pages(lesson)) + 1)), args.size, args.quality)
        did = True

    if args.import_dir:
        import_images(lesson, Path(args.import_dir))
        did = True

    if args.ok is not None:
        approve(lesson, args.ok)
        did = True

    if args.prompts or not did:
        d = write_prompts(lesson)
        print(f"✓ 提示词：{d.relative_to(common.ROOT)}/prompts.txt")
        show(lesson)
        return

    if args.prompt:
        write_prompts(lesson)
        show(lesson)


if __name__ == "__main__":
    main()
