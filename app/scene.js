/* 场景渲染：背景模板 + 精灵合成。
 *
 * 关键点：热点就是精灵本身（<g class="spot" data-ch="兔">），
 * 不存在"图片是生成的、几何关系不可知"的问题。
 */
(function (root) {
  const ORDER = [
    "sun", "moon", "cloud",
    "mountain_far", "mountain", "hill",
    "river",
    "grass", "flower", "rock",
    "stump", "tree", "farmer", "rabbit"
  ];

  const SKY = {
    day: ["#FFF3D6", "#F6DDB8"],
    dusk: ["#F8D6AC", "#E7B086"],
    night: ["#D9E3EC", "#C2D2E0"]
  };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function place(sprite, x, y, scale) {
    const base = (root.BASE_SIZE && root.BASE_SIZE[sprite]) || 100;
    const size = base * (scale == null ? 1 : scale);
    const left = (x / 100) * 1000 - size / 2;
    const top = (y / 100) * 600 - size / 2;
    return `<g transform="translate(${left.toFixed(1)},${top.toFixed(1)}) scale(${(size / 100).toFixed(3)})">${root.SPRITES[sprite] || ""}</g>`;
  }

  function decor(bg) {
    const dusk = bg === "dusk" || bg === "night";
    let out = "";
    // 固定装饰：只在边缘与天空，不抢主体的位置
    out += place("bush", 5, 86, 0.95);
    out += place("bush", 93, 86, 0.9);
    out += place("mushroom", 27, 95, 0.85);
    out += place("mushroom", 30, 97, 0.6);
    out += place("rock", 15, 94, 0.55);
    out += place("grass", 6, 96, 0.8);
    out += place("grass", 92, 95, 0.9);
    if (!dusk) {
      out += place("bird", 56, 11, 0.55);
      out += place("bird", 62, 7, 0.42);
      out += place("bird", 66, 13, 0.34);
      out += place("butterfly", 79, 73, 0.9);
    } else {
      out += place("firefly", 18, 46, 1.1);
      out += place("firefly", 30, 58, 0.8);
      out += place("firefly", 46, 38, 0.9);
      out += place("firefly", 64, 52, 0.7);
      out += place("firefly", 74, 34, 0.85);
    }
    return `<g class="decor" pointer-events="none">${out}</g>`;
  }

  function renderScene(scene, opts) {
    opts = opts || {};
    const items = (scene && scene.items) || [];
    const sky = SKY[(scene && scene.bg) || "day"] || SKY.day;

    const sorted = items.slice().sort((a, b) => {
      const ia = ORDER.indexOf(a.s), ib = ORDER.indexOf(b.s);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });

    let body = "";
    sorted.forEach(it => {
      const sprite = it.s;
      if (!root.SPRITES[sprite]) return;
      const L = (root.LAYOUT && root.LAYOUT[sprite]) || [50, 50, 1];
      const x = it.x == null ? L[0] : it.x;
      const y = it.y == null ? L[1] : it.y;
      const sc = it.scale == null ? L[2] : it.scale;
      const inner = place(sprite, x, y, sc);
      const ch = root.SPRITE_CHAR && root.SPRITE_CHAR[sprite];
      if (opts.spots && ch) {
        const cx = (x / 100) * 1000;
        const cy = (y / 100) * 600;
        const hr = Math.min(84, Math.max(38, ((root.BASE_SIZE[sprite] || 100) * sc) / 2.6));
        // 提示圈夹在画布内，避免半圆贴在边缘
        const hx = Math.min(1000 - hr - 8, Math.max(hr + 8, cx));
        const hy = Math.min(600 - hr - 8, Math.max(hr + 8, cy));
        body += `<g class="spot" data-ch="${esc(ch)}" role="button" tabindex="0" aria-label="${esc(ch)}">` +
          `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${Math.max(46, ((root.BASE_SIZE[sprite] || 100) * sc) / 2)}" fill="transparent"/>` +
          inner + `<circle class="hint" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${hr.toFixed(1)}"/>` +
          `</g>`;
      } else {
        body += inner;
      }
    });

    const anim = opts.animate === false ? "" : "scene-anim";
    return `<svg class="scene ${anim}" viewBox="0 0 1000 600" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="${sky[0]}"/>
          <stop offset="1" stop-color="${sky[1]}"/>
        </linearGradient>
        <filter id="soft"><feGaussianBlur stdDeviation="6"/></filter>
        <linearGradient id="groundG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#C4D7A4"/>
          <stop offset="55%" stop-color="#B8CE97"/>
          <stop offset="100%" stop-color="#A9C287"/>
        </linearGradient>
        <linearGradient id="hazeG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#FFF6E0" stop-opacity="0"/>
          <stop offset="100%" stop-color="#FFF6E0" stop-opacity="0.45"/>
        </linearGradient>
      </defs>
      <rect width="1000" height="600" fill="url(#sky)"/>
      <rect y="405" width="1000" height="70" fill="url(#hazeG)"/>
      <path d="M0,452 C170,438 300,462 510,450 C730,438 860,462 1000,446 L1000,600 L0,600 Z" fill="url(#groundG)"/>
      <path d="M0,452 C170,438 300,462 510,450 C730,438 860,462 1000,446" stroke="#E1EDCD" stroke-width="6" fill="none" opacity="0.9"/>
      <g opacity="0.4" stroke="#9CB77C" stroke-width="1.6" stroke-linecap="round" fill="none">
        <path d="M80,520 q3,-10 7,-13 M86,520 q1,-9 5,-12"/>
        <path d="M210,500 q3,-9 7,-12 M216,500 q0,-8 4,-11"/>
        <path d="M610,515 q3,-10 8,-13 M617,515 q1,-8 5,-11"/>
        <path d="M760,540 q3,-9 7,-12 M766,540 q1,-8 4,-11"/>
        <path d="M890,505 q3,-9 7,-12 M896,505 q1,-8 5,-11"/>
      </g>
      <g opacity="0.3" fill="#8FAC72">
        <circle cx="120" cy="548" r="3"/><circle cx="300" cy="575" r="2.2"/>
        <circle cx="420" cy="536" r="2.6"/><circle cx="700" cy="565" r="2.2"/>
        <circle cx="840" cy="545" r="2.8"/><circle cx="950" cy="575" r="2.4"/>
      </g>
      ${decor(scene && scene.bg)}
      ${body}
    </svg>`;
  }

  root.renderScene = renderScene;
  root.SCENE_ORDER = ORDER;
})(typeof window !== "undefined" ? window : globalThis);
