/* RPG 对话框运行时（SPEC v1.1 §5）。
 *
 * 只负责一件事：把 page.dialog[] 一句一句演出来。
 * 不碰课表、不碰渲染管线、不依赖任何框架；删掉 index.html 里的 <script> 即回到基线行为。
 *
 * 状态机：
 *   idle --open()--> shown(0)
 *   shown(i) --advance()--> shown(i+1)          (i < last)
 *   shown(last) --advance()--> closing --250ms--> idle
 *   closing --(250ms 到)--> idle
 *   idle --advance()--> open()
 *
 * 输入：点舞台任意处 / Enter / Space 推进，Escape 收起。
 * open 后 250ms 内与 closing 态的 advance 一律忽略（一次点击只能推一句）。
 */
(function () {
  "use strict";

  var CLOSE_MS = 250;    // closing -> idle；同时是 open 后的防抖窗口
  var SWAP_MS = 120;     // 句间淡入淡出

  var cur = null;        // { root, lesson, pageIndex }
  var st = {
    state: "idle",       // idle | shown | closing
    idx: -1,
    lockUntil: 0,
    layer: null,
    figure: null,
    who: null,
    box: null,
    nameEl: null,
    lineEl: null,
    closeTimer: null,
    swapTimer: null,
    opener: null,
    audio: null
  };
  var ac = null;         // 当前 root 上的点击监听，重渲染时先解绑

  /* ---------------- 小工具 ---------------- */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function pageOf() {
    if (!cur) return null;
    return (cur.lesson.pages || [])[cur.pageIndex] || null;
  }

  function linesOf() {
    var page = pageOf();
    var list = (page && page.dialog) || [];
    // build.py 保证运行时一定有 dialog；这里只兜底手改数据的情况
    if (!list.length && page && page.text) list = [{ who: "narrator", text: page.text }];
    return list;
  }

  // 课程级找角色：L03 只有第 1 页有 farmer 热区，后面几页的台词照样要能说话
  function actorOf(id) {
    var pages = (cur && cur.lesson.pages) || [];
    for (var i = 0; i < pages.length; i++) {
      var hs = pages[i].hotspots || [];
      for (var j = 0; j < hs.length; j++) {
        if (hs[j].id === id && hs[j].actor) return hs[j];
      }
    }
    return null;
  }

  function portraitOf(who) {
    var all = (cur && cur.lesson.portraits) || {};
    return all[who] || null;
  }

  // 肖像取 <actor>_torso.webp；素材不存在时由 onerror 回退到 hotspot 的 actor 图
  function torsoOf(src) {
    return String(src || "").replace(/(\.[a-z0-9]+)$/i, "_torso$1");
  }

  function isNarrator(who) {
    return !who || who === "narrator";
  }

  /* ---------------- 声音 ---------------- */

  function stopLine() {
    if (!st.audio) return;
    try { st.audio.pause(); st.audio.currentTime = 0; } catch (e) { /* noop */ }
    st.audio = null;
  }

  function playLine(line) {
    stopLine();
    if (!line || !line.audio) return;   // 没合成语音就静音演，不抛错
    var a = new Audio(line.audio);
    a.preload = "auto";
    a.setAttribute("playsinline", "");
    st.audio = a;
    var p = a.play();
    if (p && p.catch) p.catch(function () { /* 自动播放被拦，静音即可 */ });
  }

  /* ---------------- DOM ---------------- */

  function buildLayer() {
    var layer = document.createElement("div");
    layer.className = "dialog-layer";
    layer.setAttribute("data-state", "shown");

    var stack = document.createElement("div");
    stack.className = "dialog-stack";

    // 先放头像位；narrator 或没配肖像时整个 figure 不插进来
    var box = document.createElement("section");
    box.className = "dialog-box";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-live", "polite");
    box.tabIndex = -1;

    var nameEl = document.createElement("p");
    nameEl.className = "dialog-name";

    var lineEl = document.createElement("p");
    lineEl.className = "dialog-line";

    var text = document.createElement("div");
    text.className = "dialog-text";

    var next = document.createElement("span");
    next.className = "dialog-next";
    next.setAttribute("aria-hidden", "true");
    next.textContent = "▼";

    text.appendChild(nameEl);
    text.appendChild(lineEl);
    box.appendChild(text);
    box.appendChild(next);
    stack.appendChild(box);
    layer.appendChild(stack);

    st.layer = layer;
    st.box = box;
    st.nameEl = nameEl;
    st.lineEl = lineEl;
    return layer;
  }

  function buildAvatar(who) {
    var hs = actorOf(who);
    if (!hs) return null;                       // who 无 actor：只出文本

    var por = portraitOf(who) || {};
    var fig = document.createElement("figure");
    fig.className = "dialog-avatar";
    fig.setAttribute("data-who", who);
    fig.setAttribute("data-anchor", por.anchor === "right" ? "right" : "left");

    var img = document.createElement("img");
    img.alt = "";
    img.draggable = false;
    var actorSrc = hs.actor;
    var torsoSrc = torsoOf(actorSrc);
    // 方案 A：课程里显式给 96×96 头像；缺素材时才退回半身图，仍然不崩。
    var sources = [por.avatar, torsoSrc, actorSrc].filter(function (s, i, all) {
      return s && all.indexOf(s) === i;
    });
    var si = 0;
    if (!sources.length) return null;
    img.src = sources[si];

    img.onerror = function () {
      // avatar → torso → 整身贴纸 → 整块收掉，文本照常演。
      si += 1;
      if (si < sources.length) { img.src = sources[si]; return; }
      if (fig.parentNode) fig.parentNode.removeChild(fig);
      if (st.figure === fig) st.figure = null;
    };

    fig.appendChild(img);
    st.figure = fig;
    return fig;
  }

  function dropAvatar() {
    if (st.figure && st.figure.parentNode) st.figure.parentNode.removeChild(st.figure);
    st.figure = null;
  }

  /* ---------------- 渲染一句 ---------------- */

  function paint(i, animate) {
    var list = linesOf();
    var line = list[i];
    if (!line) return;

    var who = isNarrator(line.who) ? "narrator" : line.who;
    var hs = isNarrator(who) ? null : actorOf(who);
    var label = (hs && hs.label) || "";

    st.layer.setAttribute("data-who", who);
    if (isNarrator(who)) st.layer.removeAttribute("data-anchor");
    else st.layer.setAttribute("data-anchor", (portraitOf(who) || {}).anchor === "right" ? "right" : "left");

    function swap() {
      st.lineEl.textContent = line.text || "";
      if (isNarrator(who)) {
        st.nameEl.textContent = "";
        st.nameEl.hidden = true;
        st.box.removeAttribute("aria-label");
      } else {
        st.nameEl.textContent = label || who;
        st.nameEl.hidden = false;
        st.box.setAttribute("aria-label", label || who);
      }
      st.lineEl.classList.remove("is-swapping");
      playLine(line);
    }

    if (animate) {
      // 句间只做 120ms 透明度，纸卡不动
      st.lineEl.classList.add("is-swapping");
      clearTimeout(st.swapTimer);
      st.swapTimer = setTimeout(swap, SWAP_MS);
    } else {
      swap();
    }

    // 头像跟着谁说话换；同一个人连说两句不重建，避免 img 闪一下
    if (st.who !== who) {
      st.who = who;
      dropAvatar();
      if (!isNarrator(who)) {
        var fig = buildAvatar(who);
        if (fig) st.box.insertBefore(fig, st.box.firstChild);
      }
    }
  }

  /* ---------------- 状态切换 ---------------- */

  function open(pageIndex) {
    if (!cur) return;
    // 已经翻到 reader 页时 cur 还留着上一页的节点，别往已脱离文档的 root 上挂
    if (!cur.root || !document.contains(cur.root)) return;
    if (st.state === "shown") return;
    if (st.state === "closing") return;          // 收场中不重开，等 idle

    if (typeof pageIndex === "number") cur.pageIndex = pageIndex;
    var list = linesOf();
    if (!list.length) return;                    // 这一页没台词，整块不出现

    st.opener = document.activeElement;
    var layer = buildLayer();
    cur.root.appendChild(layer);
    st.layer.setAttribute("data-state", "shown");
    st.state = "shown";
    st.idx = 0;
    st.who = null;
    st.lockUntil = Date.now() + CLOSE_MS;        // 防止开卡那一下被同一击推进

    paint(0, false);

    // 焦点进对话框；preventScroll 防止小屏把整页顶一下
    try { st.box.focus({ preventScroll: true }); } catch (e) { st.box.focus(); }
  }

  function close() {
    if (st.state === "idle" || st.state === "closing") return;
    st.state = "closing";
    st.lockUntil = 0;
    stopLine();
    if (st.layer) st.layer.setAttribute("data-state", "closing");

    clearTimeout(st.closeTimer);
    st.closeTimer = setTimeout(function () {
      if (st.layer && st.layer.parentNode) st.layer.parentNode.removeChild(st.layer);
      st.layer = st.figure = st.box = st.nameEl = st.lineEl = null;
      st.who = null;
      st.state = "idle";
      st.idx = -1;

      // 焦点还给触发元素（默认就是舞台）
      var back = st.opener && st.opener.focus && document.contains(st.opener) ? st.opener : cur && cur.root;
      if (back && back.focus) {
        try { back.focus({ preventScroll: true }); } catch (e) { /* noop */ }
      }
      st.opener = null;
    }, CLOSE_MS);
  }

  function advance() {
    if (!cur) return;
    if (st.state === "closing") return;                    // 收场中忽略
    if (st.state === "idle") { open(); return; }           // 整页可再次唤出
    if (Date.now() < st.lockUntil) return;                 // 250ms 防抖

    var list = linesOf();
    if (st.idx < list.length - 1) {
      st.idx += 1;
      paint(st.idx, true);
    } else {
      close();
    }
  }

  /* ---------------- 输入 ---------------- */

  function onRootClick(e) {
    // 翻页按钮/页码不推进对话；其余整块舞台都是「继续」
    if (e.target.closest && e.target.closest(".nav, .pageno, .dot, #pager")) return;
    advance();
  }

  function onKey(e) {
    if (!cur) return;
    // 只在自己还占着当前页面时接管按键（翻到 reader 页后 cur 是上一页的残留）
    if (st.state === "idle" && (!cur.root || !document.contains(cur.root))) return;
    if (e.key === "Escape") {
      if (st.state !== "idle") { e.preventDefault(); close(); }
      return;
    }
    if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
    // 焦点在真正的按钮/输入上时，把键让给它（翻页、关闭选择器等）
    var t = e.target;
    if (t && t.closest && t.closest("button, a, input, select, textarea") && !t.closest(".dialog-box")) return;
    e.preventDefault();
    advance();
  }

  /* ---------------- 对外接口 ---------------- */

  window.ShiziDialog = {
    init: function (rootEl, options) {
      options = options || {};
      if (ac) { ac.abort(); ac = null; }
      clearTimeout(st.closeTimer);
      clearTimeout(st.swapTimer);
      stopLine();

      // 新一页（DOM 已整体替换）：旧 layer 已不在文档里，状态直接归零
      st.state = "idle";
      st.idx = -1;
      st.lockUntil = 0;
      st.layer = st.figure = st.box = st.nameEl = st.lineEl = null;
      st.who = null;
      st.opener = null;

      cur = {
        root: rootEl,
        lesson: options.lesson || { pages: [] },
        pageIndex: typeof options.pageIndex === "number" ? options.pageIndex : 0
      };

      if (rootEl) {
        ac = new AbortController();
        rootEl.addEventListener("click", onRootClick, { signal: ac.signal });
      }
    },

    open: open,
    advance: advance,
    close: close,

    state: function () { return st.state; },
    index: function () { return st.state === "idle" ? -1 : st.idx; }
  };

  document.addEventListener("keydown", onKey);
})();
