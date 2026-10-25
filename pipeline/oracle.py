"""象形卡字形：从开源甲骨文字形库取字，规范化成统一尺寸。

来源：github.com/zhouyongh/hanzi-glyphs-svg
  - 甲骨文 汉典批 10,213 个摹本：CC0 1.0（无义务）
  - 甲骨文 JGW 批 1,203 个骨架：CC BY 4.0（需署名）

本文件只用 CC0 的汉典批（index 里 char_form 为空、source_book 有值的那批），
不引入署名义务。取字靠 index.csv 的 modern_char → file，不硬编文件名，
因为上游增删字形时编号会整体重排。

规范化：把任意 viewBox 的字形缩放到 100×100、居中、统一线宽，
这样十几个字摆在一起大小一致。
"""
from __future__ import annotations

import csv
import io
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / ".cache"
INDEX_URL = "https://cdn.jsdelivr.net/gh/zhouyongh/hanzi-glyphs-svg@main/glyphs/oracle/index.csv"
RAW_URL = "https://cdn.jsdelivr.net/gh/zhouyongh/hanzi-glyphs-svg@main/glyphs/oracle/{file}"

# 古文字多用本字/繁体，这里做一层映射
VARIANTS = {"门": "門", "鸟": "鳥", "鱼": "魚", "云": "雲", "风": "風", "草": "艸"}

INK = "#3B352C"
STROKE_PX = 2.8      # 在 100×100 画布里的线宽
FILL_RATIO = 0.84    # 字形占画布的比例


def _get(url: str, cache: Path, timeout: int = 60) -> bytes:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 0:
        return cache.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "shizi-pipeline/1.0"})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    cache.write_bytes(data)
    return data


def load_index() -> dict[str, str]:
    """modern_char -> 文件名。同一字多形时取第一条（索引按《说文》部序排）。"""
    raw = _get(INDEX_URL, CACHE / "oracle-index.csv")
    out: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        ch = (row.get("modern_char") or "").strip()
        f = (row.get("file") or "").strip()
        if ch and f and ch not in out:
            out[ch] = f
    return out


def normalize(svg_text: str) -> str:
    vb = re.search(r'viewBox="([\d.\-\s,]+)"', svg_text)
    if not vb:
        raise ValueError("没有 viewBox，无法规范化")
    x, y, w, h = [float(v) for v in re.split(r"[\s,]+", vb.group(1).strip())]
    if not w or not h:
        raise ValueError("viewBox 宽高为 0")

    scale = (100 * FILL_RATIO) / max(w, h)
    tx = (100 - w * scale) / 2 - x * scale
    ty = (100 - h * scale) / 2 - y * scale

    paths = re.findall(r'<path[^>]*\bd="([^"]+)"', svg_text)
    if not paths:
        raise ValueError("没有 path")

    body = "".join(
        f'<path d="{d}" fill="none" stroke="{INK}" '
        f'stroke-width="{STROKE_PX / scale:.3f}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        for d in paths
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        f'role="img" aria-hidden="true"><g transform="translate({tx:.2f},{ty:.2f}) '
        f'scale({scale:.4f})">{body}</g></svg>'
    )


def fetch(char: str, index: dict[str, str] | None = None) -> str:
    index = index or load_index()
    key = char if char in index else VARIANTS.get(char)
    if not key or key not in index:
        raise KeyError(f"甲骨文库里没有「{char}」")
    fname = index[key]
    raw = _get(RAW_URL.format(file=fname), CACHE / "oracle" / fname)
    return normalize(raw.decode("utf-8"))


# 文件名用拼音，冲突的加序号（雨 yu / 鱼 yu2）。固定表比自动转写稳，
# 不依赖 pypinyin，也不会因为库版本变化而改名。
SLUGS = {
    "山": "shan", "水": "shui", "雨": "yu", "鱼": "yu2", "田": "tian",
    "门": "men", "鸟": "niao", "兔": "tu", "花": "hua", "草": "cao",
    "木": "mu", "林": "lin", "明": "ming", "大": "da", "小": "xiao",
    "上": "shang", "下": "xia",
}


def slug_of(char: str) -> str:
    return SLUGS.get(char) or ("u%04x" % ord(char))


def build(chars: str, out_dir: Path | None = None) -> dict[str, str]:
    out_dir = out_dir or (ROOT / "app" / "assets" / "picto")
    out_dir.mkdir(parents=True, exist_ok=True)
    index = load_index()
    written: dict[str, str] = {}
    for ch in chars:
        try:
            svg = fetch(ch, index)
        except Exception as e:
            print(f"  ✗ {ch}: {e}")
            continue
        slug = slug_of(ch)
        p = out_dir / f"{slug}.svg"
        p.write_text(svg, encoding="utf-8")
        written[ch] = f"assets/picto/{p.name}"
        print(f"  ✓ {ch} → {p.relative_to(ROOT)} ({len(svg)} B)")

    # 合并进索引，保留之前生成过的字
    idx_path = ROOT / "data" / "pictographs.json"
    old = {}
    if idx_path.exists():
        import json
        old = json.loads(idx_path.read_text(encoding="utf-8"))
    old.update(written)
    import json
    idx_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="从甲骨文库取象形字形")
    ap.add_argument("--chars", default="山雨水", help="要生成的字，例如 山雨水田門鳥")
    args = ap.parse_args()
    print(f"取字：{args.chars}")
    result = build(args.chars)
    print(f"完成 {len(result)} 个")
