"""从文案自动生成场景布局。

坐标来自固定布局常量（sprites.LAYOUT），不是模型估出来的。
"哪个字出现了就摆哪个元素"，所以点读热点天然对得上。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprites

CHAR_SPRITES = {
    "日": ["sun"],
    "月": ["moon"],
    "山": ["mountain_far", "mountain"],
    "水": ["river"],
    "树": ["tree", "stump"],
    "兔": ["rabbit"],
    "他": ["farmer"],
}

AMBIENT = ["cloud", "grass", "flower", "rock"]


def auto_scene(text: str, page_no: int = 1) -> dict:
    found: list[str] = []
    for ch, names in CHAR_SPRITES.items():
        if ch in text:
            found += names

    # 没提到太阳的页面也给个天光，避免画面空
    if not any(s in found for s in ("sun", "moon")):
        found.insert(0, "sun")

    names = found + AMBIENT
    # 后出现的元素放后面，保证树/人物在草丛之上（渲染时还有一层 ORDER 兜底）
    seen, items = set(), []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        x, y, sc = sprites.LAYOUT[name]
        items.append({"s": name, "x": x, "y": y, "scale": sc})

    bg = "day"
    if "月" in text:
        bg = "night"
    elif "等" in text or "没" in text:
        bg = "dusk"

    return {"bg": bg, "items": items}


if __name__ == "__main__":
    import json

    text = sys.argv[1] if len(sys.argv) > 1 else "小兔跑来，撞上树。"
    print(json.dumps(auto_scene(text), ensure_ascii=False, indent=2))
