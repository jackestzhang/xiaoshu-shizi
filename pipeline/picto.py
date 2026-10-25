"""象形图（pictograph）：让实物的轮廓承担笔画。

设计原则（来自识字卡的观察）：
1. 对称、正面、主体占 70%，四周留白；
2. 实物的外缘就是字的笔画，不加破坏轮廓的装饰；
3. 一个主色 + 一个辅色，最多三个色阶；
4. 不用文字，字另外用 HTML 叠加，保证清晰与可换字体。

输出 512×512 的 SVG，透明背景（容器给米色）。
"""
from __future__ import annotations

from pathlib import Path

W = H = 512

# 三个字的配色，取自绘本的暖色系，避免和插画打架
SAND = ("#EBB768", "#C9822F")
JADE = ("#93BCA2", "#5F8A70")
GRASS = ("#AFC98C", "#8AA76A")
CLOUD = ("#A8BCCE", "#6E859B")
RAIN = ("#63A0C4", "#3B6F91")
WATER = ("#8CC3DC", "#3E7E9E")

DEFS_COMMON = """
  <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#6B5636" flood-opacity="0.16"/>
  </filter>
"""


def _grad(gid: str, c: tuple[str, str], vertical: bool = True) -> str:
    x2, y2 = ("0", "1") if vertical else ("1", "0")
    return (
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
        f'<stop offset="0%" stop-color="{c[0]}"/>'
        f'<stop offset="100%" stop-color="{c[1]}"/>'
        f"</linearGradient>"
    )


def shan() -> str:
    """山：三峰 + 底横。中峰高，左右低，三峰落在同一条地面线上。"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="山的象形图">
  <defs>
    {_grad("g-main", SAND)}
    {_grad("g-side", JADE)}
    {_grad("g-ground", GRASS)}
    <linearGradient id="g-light" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    {DEFS_COMMON}
  </defs>

  <g filter="url(#soft)">
    <!-- 底横：整条地面，对应“山”的最后一横 -->
    <rect x="88" y="392" width="336" height="26" rx="13" fill="url(#g-ground)"/>

    <!-- 左右两峰：矮，青绿 -->
    <path d="M144,212 C168,282 190,344 212,392 L78,392 C102,338 124,276 144,212 Z" fill="url(#g-side)"/>
    <path d="M368,212 C392,276 414,338 434,392 L300,392 C322,344 344,282 368,212 Z" fill="url(#g-side)"/>
    <path d="M150,244 C166,296 180,340 194,370 L166,352 Z" fill="url(#g-light)"/>
    <path d="M362,244 C378,296 392,340 406,370 L378,352 Z" fill="url(#g-light)"/>

    <!-- 中峰：高，赭黄，侧边是缓曲线 -->
    <path d="M256,106 C286,180 318,278 344,392 L168,392 C194,278 226,180 256,106 Z" fill="url(#g-main)"/>
    <path d="M256,106 C256,200 256,320 256,392 L168,392 C194,278 226,180 256,106 Z" fill="#FFFFFF" opacity="0.09"/>
    <path d="M256,112 C272,168 288,222 300,264 L276,246 Z" fill="url(#g-light)"/>
    <!-- 雪顶：盖住峰尖三分之一，让它读作“山”而不是三角 -->
    <path d="M256,106 C270,152 284,196 296,232 L256,252 L216,228 C228,192 242,148 256,106 Z"
          fill="#FFFDF6" opacity="0.94"/>
    <path d="M256,106 C262,134 268,162 274,186 L256,200 L238,184 C244,158 250,130 256,106 Z"
          fill="#FFFFFF"/>

    <!-- 山脚的一点点草，只贴地，不碰轮廓 -->
    <g stroke="#7D9A5D" stroke-width="4" stroke-linecap="round" opacity="0.55" fill="none">
      <path d="M126,392 q4,-16 10,-22 M126,392 q-2,-14 3,-20"/>
      <path d="M392,392 q4,-15 10,-21 M392,392 q-2,-13 3,-19"/>
    </g>
  </g>
</svg>
"""


def yu() -> str:
    """雨：横向的云（上缘平直）+ 四滴雨，一对一对应“雨”的上横、框和四点。"""
    drops = []
    for cx, cy, sc in ((178, 322, 1.0), (234, 336, 0.92), (290, 336, 0.92), (346, 322, 1.0)):
        drops.append(
            f'<g transform="translate({cx},{cy}) scale({sc})">'
            f'<path d="M0,-30 C15,-9 17,7 0,18 C-17,7 -15,-9 0,-30 Z" fill="url(#g-rain)"/>'
            f'<circle cx="-5" cy="-3" r="4.4" fill="#FFFFFF" opacity="0.55"/></g>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="雨的象形图">
  <defs>
    {_grad("g-cloud", CLOUD)}
    {_grad("g-rain", RAIN)}
    {DEFS_COMMON}
  </defs>

  <g filter="url(#soft)">
    <!-- 云体：横长、上缘平直；左右两端微微下垂，承担“冂”的两边 -->
    <path d="M96,170 H416 A26,26 0 0 1 442,196 V228 A26,26 0 0 1 416,254 H96
             A26,26 0 0 1 70,228 V196 A26,26 0 0 1 96,170 Z" fill="url(#g-cloud)"/>
    <!-- 云朵起伏：只在顶部加圆弧，不打乱上缘那条直线 -->
    <g fill="url(#g-cloud)">
      <circle cx="122" cy="176" r="26"/>
      <circle cx="182" cy="162" r="32"/>
      <circle cx="246" cy="156" r="36"/>
      <circle cx="310" cy="162" r="32"/>
      <circle cx="372" cy="176" r="26"/>
    </g>
    <rect x="78" y="172" width="356" height="8" rx="4" fill="#FFFFFF" opacity="0.28"/>

    {''.join(drops)}
  </g>
</svg>
"""


def shui() -> str:
    """水：中竖钩 + 左侧一笔（横撇）+ 右侧两笔（撇、捺）。左一右二，不对称。"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="水的象形图">
  <defs>
    {_grad("g-water", WATER)}
    <linearGradient id="g-fall" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#A6D4E6"/>
      <stop offset="100%" stop-color="#3E7E9E"/>
    </linearGradient>
    <linearGradient id="g-pool" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#8CC3DC" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#3E7E9E" stop-opacity="0.08"/>
    </linearGradient>
    {DEFS_COMMON}
  </defs>

  <g filter="url(#soft)" fill="none" stroke-linecap="round">
    <!-- 涟漪 -->
    <ellipse cx="256" cy="438" rx="124" ry="21" fill="url(#g-pool)" stroke="none"/>
    <ellipse cx="256" cy="438" rx="80" ry="11" stroke="#FFFFFF" stroke-width="3" opacity="0.40"/>

    <!-- 左右三笔与主干分离：像溅开的水，而不是分叉的枝 -->
    <path d="M216,232 Q190,262 162,308" stroke="url(#g-water)" stroke-width="26"/>
    <path d="M296,180 Q322,208 356,250" stroke="url(#g-water)" stroke-width="25"/>
    <path d="M296,248 Q318,280 340,326" stroke="url(#g-water)" stroke-width="21"/>

    <!-- 中竖钩 -->
    <path d="M256,106 L256,364 Q256,414 202,420" stroke="url(#g-fall)" stroke-width="38"/>
    <path d="M244,134 L244,352" stroke="#FFFFFF" stroke-width="7" opacity="0.40"/>
    <path d="M268,152 L268,338" stroke="#FFFFFF" stroke-width="3.5" opacity="0.20"/>

    <!-- 溅起的水珠：补左侧的平衡 -->
    <g fill="url(#g-water)" stroke="none">
      <circle cx="158" cy="312" r="7" opacity="0.75"/>
      <circle cx="366" cy="262" r="7" opacity="0.75"/>
      <circle cx="336" cy="336" r="5" opacity="0.55"/>
      <circle cx="196" cy="238" r="5" opacity="0.5"/>
    </g>
  </g>
</svg>
"""


GLYPHS = {"山": ("shan", shan), "雨": ("yu", yu), "水": ("shui", shui)}


def build(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for _ch, (slug, fn) in GLYPHS.items():
        p = out_dir / f"{slug}.svg"
        p.write_text(fn(), encoding="utf-8")
        written.append(p)
    return written


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parent.parent
    files = build(root / "app" / "assets" / "picto")
    for f in files:
        print(f"✓ {f.relative_to(root)}  {f.stat().st_size} B")
