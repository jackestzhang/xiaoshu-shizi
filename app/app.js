/* 儿童端主逻辑：点读、长按大字、翻页、家长面板、听音找字。 */
(function () {
  const S = window.SHIZI;
  const T = window.ShiziTrack;
  const HANZI = /[\u4e00-\u9fff]/;

  const view = document.getElementById("view");
  const picker = document.getElementById("picker");
  const pkName = document.getElementById("pkName");
  const pkKicker = document.getElementById("pkKicker");
  const pickerWrap = document.getElementById("pickerWrap");
  const pwList = document.getElementById("pwList");
  const pwClose = document.getElementById("pwClose");
  const pwScrim = document.getElementById("pwScrim");
  const subtitle = document.getElementById("subtitle");
  const footHint = document.getElementById("footHint");
  const footStat = document.getElementById("footStat");

  const mask = document.getElementById("mask");
  const drawer = document.getElementById("drawer");
  const drawerSub = document.getElementById("drawerSub");
  const drawerBody = document.getElementById("drawerBody");

  const bigWrap = document.getElementById("bigWrap");
  const bigCard = document.getElementById("bigCard");
  const bigFace = document.getElementById("bigFace");
  const bigPic = document.getElementById("bigPic");
  const bigHint = document.getElementById("bigHint");
  const bigGlyph = document.getElementById("bigGlyph");
  const bigPy = document.getElementById("bigPy");
  const bigWord = document.getElementById("bigWord");

  const quizWrap = document.getElementById("quizWrap");
  const quizCount = document.getElementById("quizCount");
  const quizMsg = document.getElementById("quizMsg");
  const optionsEl = document.getElementById("options");
  const replayBtn = document.getElementById("replayBtn");

  const state = {
    lesson: 0,
    page: 0,
    expSeen: new Set(),
    quiz: null,
    flashEls: [],
    flashTimer: null,
    playing: null,
  };

  const audioCache = new Map();

  /* ---------------- 基础工具 ---------------- */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function current() { return S.lessons[state.lesson]; }

  // ?mode=dialog / ?mode=reader 强制切换呈现形态；其它值或没有参数时返回空串，
  // 交给课程数据里的 presentation 决定。?mode=reader 优先级最高，dialog 课也能回退。
  function forcedMode() {
    try {
      const m = new URLSearchParams(location.search).get("mode");
      return m === "dialog" || m === "reader" ? m : "";
    } catch (e) { return ""; }
  }

  function charsOf(text) { return Array.from(text || "").filter(ch => HANZI.test(ch)); }

  function unique(arr) { return Array.from(new Set(arr)); }

  function phrases(text) {
    return (text || "").match(/[^，。！？、；：]+[，。！？、；：]?/g) || [text];
  }

  function pageNo() { return current().kind === "story" ? state.page + 1 : 0; }

  function audioFor(ch) { return (S.chars[ch] || {}); }

  let toastTimer = null;
  function hideToast() {
    const el = document.getElementById("toast");
    if (!el) return;
    el.classList.remove("on");
    clearTimeout(toastTimer);
    setTimeout(() => { el.hidden = true; }, 200);
  }
  function toast(msg, retry) {
    const el = document.getElementById("toast");
    const btn = document.getElementById("toastBtn");
    if (!el) return;
    document.getElementById("toastMsg").textContent = msg;
    btn.hidden = !retry;
    btn.onclick = () => { hideToast(); if (retry) retry(); };
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add("on"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 7000);
  }

  /* ---------------- 声音 ---------------- */

  function getAudio(src) {
    if (!audioCache.has(src)) {
      const a = new Audio(src);
      a.preload = "auto";
      a.playsInline = true;
      a.setAttribute("playsinline", "");
      // 挂到 DOM 上：部分 WebView 对游离的 Audio 对象会回收或不给声
      a.style.display = "none";
      document.body.appendChild(a);
      audioCache.set(src, a);
    }
    return audioCache.get(src);
  }

  function stopAudio() {
    if (state.playing) {
      try { state.playing.pause(); state.playing.currentTime = 0; } catch (e) { /* noop */ }
      state.playing = null;
    }
  }

  function playAudio(src, onPlaying) {
    if (!src) return Promise.resolve(false);
    stopAudio();
    const a = getAudio(src);
    state.playing = a;
    return new Promise(resolve => {
      let done = false;
      const t0 = performance.now();
      a.onplaying = () => {
        if (done) return;
        done = true;
        if (onPlaying) onPlaying(Math.round(performance.now() - t0));
        resolve(true);
      };
      a.onerror = () => { if (done) return; done = true; resolve(false); };
      a.onended = () => { if (state.playing === a) state.playing = null; };
      try { a.currentTime = 0; } catch (e) { /* noop */ }
      const p = a.play();
      if (p && p.catch) p.catch(() => { if (!done) { done = true; resolve(false); } });
      setTimeout(() => { if (!done) { done = true; resolve(false); } }, 1600);
    });
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "zh-CN";
      u.rate = 0.85;
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    } catch (e) { /* noop */ }
  }

  function preload(list) {
    unique(list.filter(Boolean)).forEach(src => { if (!audioCache.has(src)) getAudio(src).load(); });
  }

  /* ---------------- 曝光 ---------------- */

  function logExposure(pageIdx) {
    const lesson = current();
    const key = lesson.id + ":" + pageIdx;
    if (state.expSeen.has(key)) return;
    state.expSeen.add(key);

    let cs;
    if (lesson.kind === "cards") cs = (lesson.cards || []).map(c => c.ch);
    else cs = charsOf((lesson.pages[pageIdx - 1] || {}).text);
    unique(cs).forEach(ch => T.log("exp", { lesson: lesson.id, page: pageIdx, ch }));
  }

  /* ---------------- 点击 / 长按 ---------------- */

  function bindPress(el, onPress, onLong) {
    const LONG = 420;
    const MOVE = 24;          // 手指接触面积大，抖动容忍度比鼠标宽
    const PALM = 80;          // 接触面积超过这个尺寸，判为手掌压屏
    let timer = null, sx = 0, sy = 0;
    let ownerId = null;       // 每个字各锁一个触点，互不干扰

    const reset = () => {
      if (timer) { clearTimeout(timer); timer = null; }
      ownerId = null;
      el.classList.remove("press");
    };

    el.addEventListener("pointerdown", e => {
      if (e.button != null && e.button > 0) return;      // 鼠标右键
      // 不按 isPrimary 过滤：手掌先压到屏幕上时，后落的食指就成了非主触点，
      // 那样孩子怎么点都没反应。改成每个字各自锁一个触点，手掌靠接触面积挡。
      if (ownerId !== null) return;                      // 这个字已有手指在按
      if (e.pointerType === "touch" && (e.width > PALM || e.height > PALM)) return;

      ownerId = e.pointerId;
      sx = e.clientX; sy = e.clientY;
      el.classList.add("press");

      // 按下就出声，不等抬起。
      // 多指触摸、手掌压屏、系统手势都会让 pointerup / pointercancel 收不到，
      // 等抬起再播放就等于让孩子"点了没反应"。
      if (onPress) onPress();

      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        el.classList.remove("press");
        if (onLong) onLong();
      }, LONG);
    });

    el.addEventListener("pointermove", e => {
      if (e.pointerId !== ownerId) return;
      // 划走了就取消长按（声音已经出过，收不回来，但至少不会误弹大字卡）
      if (Math.abs(e.clientX - sx) > MOVE || Math.abs(e.clientY - sy) > MOVE) reset();
    });

    el.addEventListener("pointerup", e => {
      if (e.pointerId === ownerId) reset();
    });

    el.addEventListener("pointercancel", e => {
      if (e.pointerId === ownerId) reset();
    });

    // 只有鼠标才用 leave 收尾；触摸时手指稍微移出元素边界是常态
    el.addEventListener("pointerleave", e => {
      if (e.pointerType === "mouse" && e.pointerId === ownerId) reset();
    });

    el.addEventListener("contextmenu", e => e.preventDefault());

    el.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (onPress) onPress();
      }
    });
  }

  /* ---------------- 点读 ---------------- */

  let flashSeq = 0;

  // 只高亮被点的那一个元素。同一页出现多个相同字时，不再连带全亮。
  function flash(ch, target) {
    const seq = ++flashSeq;
    clearTimeout(state.flashTimer);
    state.flashEls.forEach(el => el.classList.remove("lit", "active"));

    const els = target
      ? [target]
      : Array.from(document.querySelectorAll('button.ch[data-ch="' + ch + '"]'));
    els.forEach(el => el.classList.add("lit"));
    state.flashEls = els;

    state.flashTimer = setTimeout(() => {
      if (seq !== flashSeq) return;  // 期间又点了别的字，让新的那轮负责收尾
      els.forEach(el => el.classList.remove("lit"));
      state.flashEls = [];
    }, 1200);
  }

  function tapChar(ch, el) {
    const lesson = current();
    const readBtn = document.getElementById("readall");
    if (readBtn) readBtn.classList.remove("playing");
    const meta = audioFor(ch);
    flash(ch, el);
    playAudio(meta.audio, lat => {
      T.log("tap", { lesson: lesson.id, page: pageNo(), ch, lat });
      updateFoot();
    }).then(ok => {
      if (!ok) {
        speak(ch);
        T.log("tap", { lesson: lesson.id, page: pageNo(), ch, lat: null });
        updateFoot();
        toast("这一段没播出声音", () => tapChar(ch, el));
      }
    });
  }

  function tapWord(word, ch) {
    const meta = audioFor(ch);
    if (meta.wordAudio) playAudio(meta.wordAudio);
    T.log("word", { lesson: current().id, page: pageNo(), ch });
  }

  let bigCh = null;
  let bigMode = "char";   // char | pic

  function renderBig() {
    const meta = bigCh ? audioFor(bigCh) : {};
    const hasPic = !!meta.pictograph;
    const showPic = bigMode === "pic" && hasPic;
    bigFace.hidden = showPic;
    bigPic.hidden = !showPic;
    if (showPic) {
      const g = meta.pictograph;
      bigPic.innerHTML = g.kind === "svg" ? g.src : '<img src="' + esc(g.src) + '" alt="">';
    }
    bigHint.hidden = !hasPic || showPic;
    bigCard.classList.toggle("show-pic", showPic);
  }

  function toggleBig() {
    const meta = bigCh ? audioFor(bigCh) : {};
    if (!meta.pictograph) return;
    bigMode = bigMode === "pic" ? "char" : "pic";
    renderBig();
  }

  // 长按弹卡时手指还压在字上，抬手的瞬间浏览器会补一个 click 落在浮层上，
  // 卡片会当场被关掉。用「下一次 pointerdown」作为用户的新意图：同一次按压
  // 补出来的 click 没有新的 pointerdown，就被吞掉。
  let swallowBigClick = false;

  function showBig(ch) {
    const meta = audioFor(ch);
    if (!meta.pinyin) return;
    T.log("long", { lesson: current().id, page: pageNo(), ch });
    swallowBigClick = true;
    bigCh = ch;
    bigMode = "char";
    bigGlyph.textContent = ch;
    bigPy.textContent = meta.pinyin || "";
    bigWord.textContent = meta.word || "";
    renderBig();
    bigWrap.hidden = false;
    requestAnimationFrame(() => bigWrap.classList.add("on"));
    // 不设定时器：长按弹出的卡片一直留着，孩子想看多久看多久，
    // 收起只由「点旁边的空白」或 Esc 决定。
  }

  function hideBig() {
    bigMode = "char";
    bigPic.hidden = true;
    bigPic.innerHTML = "";
    bigWrap.classList.remove("on");
    setTimeout(() => { bigWrap.hidden = true; }, 180);
  }

  /* ---------------- 课程渲染 ---------------- */

  function shortTitle(l) {
    if (l.kind === "cards") return (l.cards || []).map(c => c.ch).join(" ");
    return l.title;
  }

  // 顶栏胶囊只显示当前这本；所有课都收进浮层里，省下一整行
  function renderPicker() {
    const cur = current();
    const curCards = cur.kind === "cards";
    pkKicker.textContent = curCards ? "字卡" : "故事";
    pkName.textContent = curCards ? "第 " + (cur.order || 1) + " 组" : shortTitle(cur);

    pwList.innerHTML = S.lessons.map((l, i) => {
      const isCards = l.kind === "cards";
      // 字卡课没有故事名，用这一组里的字当名字，比「第 1 组」好认
      const name = isCards ? (l.cards || []).map(c => c.ch).join("") : shortTitle(l);
      const meta = isCards
        ? "字卡 · " + (l.cards || []).length + " 个字"
        : l.pages.length + " 页 · " + l.pages.reduce((n, p) => n + charsOf(p.text).length, 0) + " 字";
      const ic = isCards ? "字" : (shortTitle(l)[0] || "书");
      return '<button class="pick-item' + (i === state.lesson ? " on" : "") + '" data-i="' + i + '" role="option" aria-selected="' + (i === state.lesson) + '">' +
          '<span class="pi-ic" aria-hidden="true">' + esc(ic) + '</span>' +
          '<span class="pi-main">' +
            '<span class="pi-name">' + esc(name) + '</span>' +
            '<span class="pi-meta">' + esc(meta) + '</span>' +
          '</span>' +
          '<span class="pi-tick" aria-hidden="true">✓</span>' +
        '</button>';
    }).join("");

    pwList.querySelectorAll(".pick-item").forEach(btn => {
      btn.addEventListener("click", () => {
        selectLesson(Number(btn.dataset.i));
        closePicker();
      });
    });
  }

  function openPicker() {
    renderPicker();
    pickerWrap.hidden = false;
    picker.setAttribute("aria-expanded", "true");
    const on = pwList.querySelector(".pick-item.on");
    if (on) on.scrollIntoView({ block: "nearest" });
  }

  function closePicker() {
    pickerWrap.hidden = true;
    picker.setAttribute("aria-expanded", "false");
  }

  function selectLesson(i) {
    state.lesson = i;
    state.page = 0;
    renderPicker();
    render();
    try { localStorage.setItem("shizi.last", String(i)); } catch (e) { /* noop */ }
  }

  function render() {
    const lesson = current();
    // 换课/翻页时把大字卡收掉，否则它会挡住整页
    if (!bigWrap.hidden) hideBig();
    if (subtitle) subtitle.textContent = lesson.kind === "cards" ? "先认这几个字" : "点字听声音";
    footHint.textContent = lesson.kind === "cards" ? "轻点听音 · 长按看大字" : "轻点字听声音 · 长按看大字";
    if (lesson.kind === "cards") renderCards(lesson); else renderStory(lesson);
    updateFoot();
  }

  function artPlaceholder(page) {
    return '<div class="art-missing">' +
      '<svg viewBox="0 0 120 90" aria-hidden="true">' +
        '<rect x="4" y="6" width="112" height="78" rx="12" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="5 7" opacity=".55"/>' +
        '<circle cx="86" cy="30" r="9" fill="currentColor" opacity=".35"/>' +
        '<path d="M18,70 L44,38 L60,58 L74,44 L102,70 Z" fill="currentColor" opacity=".22"/>' +
      '</svg>' +
      '<b>插画待生成</b>' +
      '<span>第 ' + (state.page + 1) + ' 页 · 提示词已就绪</span>' +
    '</div>';
  }

  function phrasesMarkup(text) {
    return '<div class="flow">' + phrases(text).map(ph => {
      const cs = Array.from(ph);
      let out = "";
      for (let i = 0; i < cs.length; i++) {
        const ch = cs[i];
        if (!HANZI.test(ch)) { out += '<span class="punct">' + esc(ch) + '</span>'; continue; }
        let tail = "";
        while (i + 1 < cs.length && !HANZI.test(cs[i + 1])) tail += cs[++i];
        out += '<button class="ch" data-ch="' + ch + '" aria-label="' + ch + '">' + ch +
          (tail ? '<span class="punct-in">' + esc(tail) + '</span>' : "") + '</button>';
      }
      return '<span class="phrase">' + out + '</span>';
    }).join("") + '</div>';
  }

  function renderStory(lesson) {
    // 唯一分派点：dialog 课或 ?mode=dialog 交给对话框运行时；
    // ?mode=reader 优先，dialog 课也走下面原样的 reader 实现。
    const mode = forcedMode();
    if (mode !== "reader" && (lesson.presentation === "dialog" || mode === "dialog")) {
      return renderDialog(lesson);
    }
    const page = lesson.pages[state.page];
    clearTimeout(bubbleTimer);
    // 标点跟着前一个字走：flex 布局下独立的标点会被挤到下一行开头，
    // 变成「……田里 / ，」这种断句。塞进前一个字的按钮里就再也分不开了。
    const phrasesHtml = phrasesMarkup(page.text);

    const art = page.art && page.art.file;
    // 舞台里先放一块「图板」：尺寸等于插画在卡片里被 cover 之后的真实矩形，
    // 角色和热点都按原图百分比挂在这块板上，转屏、换尺寸都不用重算。
    const sceneHtml = art
      ? '<div class="plate" id="plate">' +
          '<img class="art" src="' + esc(art) + '" alt="" draggable="false">' +
          '<div class="actors" id="actors">' + actorsMarkup(page) + '</div>' +
          '<div class="spots" id="spots"></div>' +
        '</div>'
      : artPlaceholder(page);

    const nChars = charsOf(page.text).length;
    // 一屏定版：图在舞台里等比缩放，字在文字卡里二分求字号，两边都不滚动
    view.innerHTML =
      '<section class="story' + (nChars <= 8 ? " is-short" : "") + '">' +
        '<div class="stage" id="stage">' +
          '<div class="scene-card">' +
            '<div class="scene" id="scene">' + sceneHtml + '</div>' +
            '<div class="bubble" id="bubble" hidden></div>' +
            (page.hotspots && page.hotspots.length
              ? '<div class="spot-chip" id="spotChip"></div>' : "") +
            '<div class="pageno">' + (state.page + 1) + " / " + lesson.pages.length + '</div>' +
            '<button class="nav prev" id="prev" aria-label="上一页"' + (state.page === 0 ? " disabled" : "") + '>‹</button>' +
            '<button class="nav next" id="next" aria-label="下一页"' + (state.page === lesson.pages.length - 1 ? " disabled" : "") + '>›</button>' +
          '</div>' +
        '</div>' +
        '<div class="textcard">' +
          '<div class="textline" id="textline">' + phrasesHtml + '</div>' +
          '<div class="cardfoot">' +
            '<div class="pager" id="pager">' + lesson.pages.map((_, i) =>
              '<button class="dot' + (i === state.page ? " on" : "") + '" data-p="' + i + '" aria-label="第 ' + (i + 1) + ' 页"></button>'
            ).join("") + '</div>' +
            '<button class="readall" id="readall">' +
              '<svg class="spk" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4Z" fill="currentColor"/></svg>读一遍</button>' +
          '</div>' +
        '</div>' +
      '</section>';

    document.querySelectorAll("#textline .ch").forEach(el => {
      const ch = el.dataset.ch;
      bindPress(el, () => tapChar(ch, el), () => showBig(ch));
    });

    document.querySelectorAll(".actor").forEach(el => {
      const hs = (page.hotspots || []).find(h => h.id === el.dataset.id);
      if (!hs) return;
      el.addEventListener("pointerdown", e => {
        e.preventDefault();                   // 别再补一个 click 出去
        e.stopPropagation();
        tapActor(hs, el);
      });
      el.addEventListener("contextmenu", e => e.preventDefault());
      startIdle(el);
    });

    document.getElementById("prev").addEventListener("click", () => turn(-1));
    document.getElementById("next").addEventListener("click", () => turn(1));
    document.querySelectorAll(".dot").forEach(d => {
      d.addEventListener("click", () => goPage(Number(d.dataset.p)));
    });
    document.getElementById("readall").addEventListener("click", readAll);

    logExposure(state.page + 1);
    preload([page.audio].concat(charsOf(page.text).map(ch => audioFor(ch).audio)));
    paintSpots(page);
    relayout();
    const artImg = document.querySelector("#scene img.art");
    if (artImg && !artImg.complete) artImg.addEventListener("load", relayout, { once: true });
  }

  /* ---------------- 对话框（RPG） ---------------- */

  // 与 reader 共用同一份课程与音频，只是把「字卡 + 点字」换成「点画面推进台词」。
  // 舞台结构（.stage/.scene-card/#plate）保持不变，fitStage/layoutPlate 不必另写一套；
  // 不渲染 hotspot、不渲染可点字，整块舞台交给 ShiziDialog 当推进按钮。
  function renderDialog(lesson) {
    const page = lesson.pages[state.page];
    clearTimeout(bubbleTimer);
    footHint.textContent = "点画面 · 一句一句听";

    const art = page.art && page.art.file;
    // p1 的底图是抠掉人物后的补洞图；把同一套 rig 贴回去，既盖住补洞，
    // 又保留呼吸 / 锄地 / 沉腰 / 直腰。p2-p7 的原画本身带农夫，不能再叠。
    const hasActors = (page.hotspots || []).some(hs => hs.actor);
    const sceneHtml = art
      ? '<div class="plate" id="plate">' +
          '<img class="art" src="' + esc(art) + '" alt="" draggable="false">' +
          (hasActors ? '<div class="actors" id="actors">' + actorsMarkup(page) + '</div>' : '') +
        '</div>'
      : artPlaceholder(page);

    view.innerHTML =
      '<section class="story is-dialog" style="grid-template-rows:minmax(0,1fr)">' +
        '<div class="stage" id="stage">' +
          '<div class="scene-card" id="sceneCard">' +
            '<div class="scene" id="scene">' + sceneHtml + '</div>' +
            '<div class="pageno">' + (state.page + 1) + " / " + lesson.pages.length + '</div>' +
            '<button class="nav prev" id="prev" aria-label="上一页"' + (state.page === 0 ? " disabled" : "") + '>‹</button>' +
            '<button class="nav next" id="next" aria-label="下一页"' + (state.page === lesson.pages.length - 1 ? " disabled" : "") + '>›</button>' +
          '</div>' +
        '</div>' +
      '</section>';

    document.getElementById("prev").addEventListener("click", () => turn(-1));
    document.getElementById("next").addEventListener("click", () => turn(1));

    const card = document.getElementById("sceneCard");
    if (window.ShiziDialog) {
      ShiziDialog.init(card, { lesson: lesson, pageIndex: state.page });
    }

    // dialog 模式里角色不可点（整块舞台负责推进台词），但 rig 的空闲动画照跑。
    // 同时移出 Tab 顺序，免得键盘用户停在看不见的角色按钮上。
    document.querySelectorAll("#actors .actor").forEach(el => {
      el.tabIndex = -1;
      el.setAttribute("aria-hidden", "true");
      startIdle(el);
    });

    logExposure(state.page + 1);
    preload((page.dialog || []).map(d => d.audio).concat([page.audio]));
    relayout();
    const artImg = document.querySelector("#scene img.art");
    if (artImg && !artImg.complete) artImg.addEventListener("load", relayout, { once: true });
  }

  /* ---------------- 图上的角色与物品 ---------------- */

  const spotsSeen = new Set();     // lessonId:page:spotId，本次打开内有效
  let bubbleTimer = null;

  const spotKey = hs => current().id + ":" + state.page + ":" + hs.id;

  function updateSpotChip(list) {
    const chip = document.getElementById("spotChip");
    if (!chip) return;
    const n = list.filter(hs => spotsSeen.has(spotKey(hs))).length;
    chip.textContent = n === 0 ? "点一点图上的人和东西"
      : n === list.length ? "都点过啦" : n + " / " + list.length;
    chip.classList.toggle("done", n === list.length);
  }

  // 图上可点的人和东西。带 actor 的不画圆点——它本身就是一张会动的贴纸，
  // 直接贴在图上，按原图百分比定位，所以不需要换算 cover 的裁切偏移。
  function actorsMarkup(page) {
    return (page.hotspots || []).filter(hs => hs.actor).map(hs => {
      // 带 rig 的角色拆成三段：下半身、上身（头+躯干）、臂（袖子+手+锄）。
      // 上身绕腰转，臂在上身里再绕肩转——两级串联，锄头才甩得开。
      // 没有 rig 的还是一张整贴纸。
      const rig = hs.rig;
      let inner;
      if (rig && rig.arm) {
        // 上身两层的画布比整图大一圈（锄头要甩得开），所以按 pad/zoom
        // 把它放大、左上各外扩回去，内容才对得上原位。
        const box = rig.zoom
          ? ' style="width:' + rig.zoom + '%;left:-' + rig.pad + '%;top:-' + rig.pad + '%"'
          : '';
        inner = '<img class="lower" src="' + esc(rig.lower) + '" alt="" draggable="false">' +
          '<span class="upper" style="transform-origin:' + rig.waist[0] + '% ' + rig.waist[1] + '%">' +
            '<img class="torso" src="' + esc(rig.torso) + '" alt="" draggable="false"' + box + '>' +
            '<span class="arm" style="transform-origin:' + rig.shoulder[0] + '% ' + rig.shoulder[1] + '%">' +
              '<img class="armimg" src="' + esc(rig.arm) + '" alt="" draggable="false"' + box + '>' +
            '</span>' +
          '</span>';
      } else if (rig) {
        inner = '<img class="lower" src="' + esc(rig.lower) + '" alt="" draggable="false">' +
          '<span class="upper" style="transform-origin:' + rig.waist[0] + '% ' + rig.waist[1] + '%">' +
            '<img src="' + esc(rig.upper) + '" alt="" draggable="false"></span>';
      } else {
        inner = '<img class="skin" src="' + esc(hs.actor) + '" alt="" draggable="false">';
      }
      return '<button class="actor' + (rig ? " rig" : "") + '" data-id="' + esc(hs.id) +
        '" aria-label="' + esc(hs.label) + '"' +
        ' style="left:' + round2(hs.x - hs.w / 2) + '%;top:' + round2(hs.y - hs.h / 2) +
        '%;width:' + round2(hs.w) + '%">' +
        '<span class="body">' + inner + '</span>' +
      '</button>';
    }).join("");
  }

  const round2 = v => Math.round(v * 100) / 100;

  function paintSpots(page) {
    const wrap = document.getElementById("spots");
    const list = (page.hotspots || []).filter(hs => !hs.actor);
    if (!wrap) return;
    wrap.innerHTML = "";
    // 挂在角色身上的热点（比如他手里那把锄头）会跟着关节一起动，
    // 否则锄头抡下去了，橙点还留在原地。有臂关节就挂臂，没有再退回上身。
    document.querySelectorAll(".actor .spot").forEach(e => e.remove());
    list.forEach(hs => {
      const host = hs.inRig && document.querySelector('.actor.rig[data-id="' + hs.inRig + '"]');
      const inRig = host ? (host.querySelector(".arm") || host.querySelector(".upper")) : null;
      const b = document.createElement(inRig ? "div" : "button");
      if (inRig) { b.setAttribute("role", "button"); b.tabIndex = 0; b.style.display = "block"; }
      b.className = "spot" + (inRig ? " in-rig" : "") + (spotsSeen.has(spotKey(hs)) ? " seen" : "");
      // 挂在上身里的热点仍按整图的百分比写。上身的图虽然被放大并外扩过
      // （给锄头留摆动空间），但外扩量和放大倍数刚好抵消，坐标不变。
      b.style.left = round2(hs.x - hs.w / 2) + "%";
      b.style.top = round2(hs.y - hs.h / 2) + "%";
      b.style.width = round2(hs.w) + "%";
      b.style.height = round2(hs.h) + "%";
      b.dataset.id = hs.id;
      b.setAttribute("aria-label", hs.label);
      b.addEventListener("pointerdown", e => {
        e.preventDefault();                   // 别再补一个 click 出去
        e.stopPropagation();
        tapSpot(hs, b);
      });
      b.addEventListener("contextmenu", e => e.preventDefault());
      (inRig || wrap).appendChild(b);
    });
    updateSpotChip(page.hotspots || []);
  }

  function tapSpot(hs, el) {
    const lesson = current();
    spotsSeen.add(spotKey(hs));
    el.classList.add("seen", "hit");
    setTimeout(() => el.classList.remove("hit"), 420);
    T.log("spot", { lesson: lesson.id, page: state.page + 1, ch: hs.id });
    showBubble(hs, el);
    updateSpotChip(lesson.pages[state.page].hotspots || []);

    playAudio(hs.audio).then(ok => {
      if (!ok && hs.line) speak(hs.line);
    });
  }

  /* ---------------- 会动的角色：一张贴纸 + 形变 ----------------
     没有关节，所以只能整体动：呼吸是纵向轻微拉伸 + 一点点上下浮动；
     被点的时候用「压—弹」演一下锄地。幅度都不大，但足够让这张图活过来。 */

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const busyActors = new WeakSet();
  const wait = ms => new Promise(r => setTimeout(r, ms));

  // 锄了一阵，直起腰看看远处有没有兔子，再弯下去接着锄。
  // 这件事本身没什么，但它说明腰和肩是两级独立的关节：腰往上抬的同时，
  // 肩得反过来压一点，锄头才不会跟着甩到天上去。
  async function straighten(el) {
    const up = el.querySelector(".upper");
    const arm = el.querySelector(".arm");
    const low = el.querySelector(".lower");
    if (!up || !arm || busyActors.has(el) || !document.contains(el)) return;
    busyActors.add(el);
    const idle = el._idle, idleArm = el._idleArm, idleLow = el._idleLow;
    try {
      if (idle) idle.pause();
      if (idleArm) idleArm.pause();
      if (idleLow) idleLow.pause();
      const w0 = angleOf(up), a0 = angleOf(arm);
      // 4.6 秒里：抬（0-38%）→ 站着（38-70%）→ 弯回去（100%）。
      // 三个动画等长，才不会出现「腰已经直了、手臂还在半路」的半截姿态。
      const opts = { duration: 4600, easing: "ease-in-out" };
      await Promise.all([
        up.animate([
          { transform: "rotate(" + w0 + "deg)" },
          { transform: "rotate(3.2deg)", offset: .38 },
          { transform: "rotate(3.2deg)", offset: .70 },
          { transform: "rotate(-2deg)" }
        ], opts).finished.catch(() => {}),
        arm.animate([
          { transform: "rotate(" + a0 + "deg)" },
          { transform: "rotate(" + Math.max(a0 - 4, 0) + "deg)", offset: .38 },
          { transform: "rotate(" + Math.max(a0 - 4, 0) + "deg)", offset: .70 },
          { transform: "rotate(0deg)" }
        ], opts).finished.catch(() => {}),
        low ? low.animate([
          { transform: "scaleY(1)" },
          { transform: "scaleY(1)" }
        ], opts).finished.catch(() => {}) : Promise.resolve()
      ]);
    } finally {
      // 停在 -2°，正是待机循环里那五分之一秒的静止姿态，接回去无缝。
      if (idle) idle.play();
      if (idleArm) idleArm.play();
      if (idleLow) idleLow.play();
      busyActors.delete(el);
    }
  }

  // 直腰只在待机循环的「静止段」起手，否则一暂停就卡在弯腰的最低点，
  // 再从那儿弹回 -2° 会抖一下。9 秒后先探，没到静止段就每 0.4 秒再看。
  function scheduleStraighten(el, delay) {
    clearTimeout(el._straightenTimer);
    el._straightenTimer = setTimeout(async () => {
      if (!document.contains(el)) return;
      const idle = el._idle;
      const t = idle ? idle.currentTime % 5600 : 0;
      if (idle && !(t > 4880 && t < 5500) || busyActors.has(el)) {
        scheduleStraighten(el, 400);
        return;
      }
      await straighten(el);
      scheduleStraighten(el, 7000 + Math.random() * 6000);
    }, delay);
  }

  function startIdle(el) {
    if (reduceMotion.matches) return;
    // 三段式角色：腰和肩两级关节。腰负责整个人的俯仰，肩负责甩臂。
    // 锄一下是一个完整的呼吸周期——慢慢抬起来、停一下、砸下去、直腰。
    const up = el.querySelector(".upper");
    if (up) {
      const arm = el.querySelector(".arm");
      const low = el.querySelector(".lower");
      // 腰沉多少、腿就压多少：translateY 的 2% 正好对上 scaleY 掉的 6%
      // （上身盒子高 382、下半身内容高 130，6% × 130 ≈ 2% × 382）。
      // 腿不压，人弯下去就成了「上半身插进裤子里」。
      el._idle = up.animate([
        { transform: "translateY(0%) rotate(-2deg)" },
        { transform: "translateY(0%) rotate(-3.4deg)", offset: .30 },
        { transform: "translateY(2%) rotate(-6.6deg)", offset: .52, easing: "cubic-bezier(.45,0,.9,.35)" },
        { transform: "translateY(2%) rotate(-6.6deg)", offset: .60, easing: "cubic-bezier(.5,0,1,.4)" },
        { transform: "translateY(0%) rotate(-1.2deg)", offset: .70 },
        { transform: "translateY(0%) rotate(-2.4deg)", offset: .78 },
        { transform: "translateY(0%) rotate(-2deg)", offset: .88 },
        { transform: "translateY(0%) rotate(-2deg)" }
      ], { duration: 5600, iterations: Infinity, easing: "ease-in-out" });
      if (low) {
        el._idleLow = low.animate([
          { transform: "scaleY(1)" },
          { transform: "scaleY(1)", offset: .30 },
          { transform: "scaleY(.94)", offset: .52 },
          { transform: "scaleY(.94)", offset: .60 },
          { transform: "scaleY(1)", offset: .78 },
          { transform: "scaleY(1)" }
        ], { duration: 5600, iterations: Infinity, easing: "ease-in-out" });
      }
      if (arm) {
        // 臂比腰早一点点起、晚一点点收，两级关节错开才有「甩」的感觉；
        // 完全同步就成了一根刚体。
        el._idleArm = arm.animate([
          { transform: "rotate(0deg)" },
          { transform: "rotate(-2.6deg)", offset: .28 },
          { transform: "rotate(-9.6deg)", offset: .52, easing: "cubic-bezier(.45,0,.9,.35)" },
          { transform: "rotate(-9.6deg)", offset: .60, easing: "cubic-bezier(.5,0,1,.4)" },
          { transform: "rotate(7.6deg)", offset: .70 },
          { transform: "rotate(2.2deg)", offset: .79 },
          { transform: "rotate(0deg)", offset: .90 },
          { transform: "rotate(0deg)" }
        ], { duration: 5600, iterations: Infinity, easing: "ease-in-out" });
      }
      scheduleStraighten(el, 6000);
      return;
    }
    const body = el.querySelector(".body");
    if (!body) return;
    // 支点在脚底：拉长和侧身都不会让脚离地。幅度比第一版大一倍，
    // 静止观察三五秒就能看出他在呼吸、重心在换脚。
    el._idle = body.animate([
      { transform: "translateY(0) scaleY(1) rotate(0deg)" },
      { transform: "translateY(-.7%) scaleY(1.022) rotate(-.35deg)", offset: .5 },
      { transform: "translateY(0) scaleY(1) rotate(0deg)" }
    ], { duration: 3600, iterations: Infinity, easing: "ease-in-out" });

    // 每八秒偏一下头，像在地里干活时抬眼看了看远处。呼吸是连续的小幅，
    // 「偏头」是间歇的明显动作——只有前者，看十秒会觉得他在原地发呆。
    el._peek = el.animate([
      { transform: "rotate(0deg)", offset: 0 },
      { transform: "rotate(.9deg)", offset: .10 },
      { transform: "rotate(.9deg)", offset: .20 },
      { transform: "rotate(0deg)", offset: .30 },
      { transform: "rotate(0deg)", offset: 1 }
    ], { duration: 8000, iterations: Infinity, easing: "ease-in-out" });
  }

  // 一张贴纸没有关节，能做的只有整体位移和形变。这里只用「压—弹」：
  // 压下去是锄头落进土里，弹回来是人直了直腰。支点在脚底，两只脚始终
  // 踩在地上，身后补出来的那块背景也一直被他挡住。
  const CHOP = [
    { transform: "none" },
    { transform: "translateY(5px) scaleY(.94)", offset: .28 },
    { transform: "translateY(-3px) scaleY(1.025)", offset: .64 },
    { transform: "none" }
  ];

  function chop(body, ms) {
    return body.animate(CHOP, { duration: ms, easing: "ease-in-out", fill: "forwards" });
  }

  const angleOf = el => {
    const m = new DOMMatrix(getComputedStyle(el).transform);
    return Math.atan2(m.b, m.a) * 180 / Math.PI;
  };
  // 同一个元素上还有 translateY / scaleY，点下去的那一刻得从「现在停在哪」
  // 接上，否则会先弹回原位再演——待机动画暂停时正卡在弯腰的低点上。
  const tyOf = el => new DOMMatrix(getComputedStyle(el).transform).f;
  const syOf = el => new DOMMatrix(getComputedStyle(el).transform).d || 1;

  // 锄刃入土的位置：热点是挂在臂上的，臂转到哪儿它就跟到哪儿，
  // 所以落地那一刻读它的实时位置最准，不用手算圆弧。
  function dust(actor) {
    const layer = document.querySelector(".actors");
    const spot = actor.querySelector('.spot[data-id="hoe"]');
    if (!layer || !spot) return;
    const b = spot.getBoundingClientRect(), h = layer.getBoundingClientRect();
    if (!h.width) return;
    const x = (b.left + b.width / 2 - h.left) / h.width * 100;
    const y = (b.top + b.height * .78 - h.top) / h.height * 100;
    for (let i = 0; i < 4; i++) {
      const d = document.createElement("span");
      d.className = "dust";
      d.style.left = x + "%";
      d.style.top = y + "%";
      d.style.setProperty("--dx", ((i - 1.5) * 9 + (Math.random() - .5) * 5).toFixed(1) + "px");
      d.style.animationDelay = (i * 26) + "ms";
      d.style.width = (1.1 + Math.random() * .9).toFixed(2) + "%";
      layer.appendChild(d);
      d.addEventListener("animationend", () => d.remove());
    }
  }

  // 盯着腰的角度，走到最深的那一格就崩一下土。
  function impactAt(up, deepWaist, ms) {
    const actor = up.closest(".actor");
    const t0 = performance.now();
    let fired = false;
    const tick = () => {
      if (fired) return;
      if (Math.abs(angleOf(up) - deepWaist) < .8) {
        fired = true;
        dust(actor);
        return;
      }
      if (performance.now() - t0 < ms * .8) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // 抬起来→停半拍→砸下去→直腰。腰和肩同时演，但肩的幅度更大一点，
  // 这样锄头落点的那一下有「手腕甩出去」的重量感。腿跟着沉：锄刃入土，
  // 重心必须一起下去，否则只是上半身在鞠躬。
  function swingOnce(up, arm, low, deepWaist, deepArm, ms) {
    const w0 = angleOf(up), a0 = arm ? angleOf(arm) : 0;
    const h = up.getBoundingClientRect().height || 1;
    const t0 = tyOf(up) / h * 100, tDeep = 2.4;
    const s0 = low ? syOf(low) : 1;
    const w = up.animate([
      { transform: "translateY(" + t0 + "%) rotate(" + w0 + "deg)" },
      { transform: "translateY(" + tDeep + "%) rotate(" + deepWaist + "deg)", offset: .44, easing: "cubic-bezier(.4,0,.7,.5)" },
      { transform: "translateY(" + tDeep + "%) rotate(" + (deepWaist + .5) + "deg)", offset: .52, easing: "cubic-bezier(.55,0,1,.4)" },
      { transform: "translateY(" + t0 + "%) rotate(-1.4deg)", offset: .62 },
      { transform: "translateY(" + t0 + "%) rotate(-2.4deg)", offset: .74 },
      { transform: "translateY(" + t0 + "%) rotate(-2deg)", offset: .88 },
      { transform: "translateY(" + t0 + "%) rotate(-2deg)" }
    ], { duration: ms, easing: "ease-in-out" });
    const a = arm ? arm.animate([
      { transform: "rotate(" + a0 + "deg)" },
      { transform: "rotate(" + deepArm + "deg)", offset: .44, easing: "cubic-bezier(.4,0,.7,.5)" },
      { transform: "rotate(" + (deepArm + .6) + "deg)", offset: .52, easing: "cubic-bezier(.55,0,1,.4)" },
      { transform: "rotate(9.4deg)", offset: .62 },
      { transform: "rotate(1.4deg)", offset: .74 },
      { transform: "rotate(0deg)", offset: .88 },
      { transform: "rotate(0deg)" }
    ], { duration: ms, easing: "ease-in-out" }) : null;
    const l = low ? low.animate([
      { transform: "scaleY(" + s0 + ")" },
      { transform: "scaleY(.93)", offset: .44, easing: "cubic-bezier(.4,0,.7,.5)" },
      { transform: "scaleY(.93)", offset: .52 },
      { transform: "scaleY(" + s0 + ")", offset: .64 },
      { transform: "scaleY(" + s0 + ")" }
    ], { duration: ms, easing: "ease-in-out" }) : null;
    // 入土那一刻起尘。不按时间猜——缓动曲线让「最深」那一格的墙钟时间
    // 每次都不太一样，盯着腰的角度走到最深再放，位置才对得上。
    const actor = up.closest(".actor");
    if (actor) impactAt(up, deepWaist, ms);
    return Promise.all([
      w.finished.catch(() => {}),
      a ? a.finished.catch(() => {}) : Promise.resolve(),
      l ? l.finished.catch(() => {}) : Promise.resolve()
    ]);
  }

  // 连着锄两下：第一下重，第二下轻，抬起来的时候正好开口说话
  async function hoeTwice(up, arm, low) {
    await swingOnce(up, arm, low, -7.4, -12.4, 780);
    await swingOnce(up, arm, low, -6.6, -10.2, 640);
  }

  async function tapActor(hs, el) {
    const lesson = current();
    const pageSpots = lesson.pages[state.page].hotspots || [];
    const firstTime = !spotsSeen.has(spotKey(hs));
    spotsSeen.add(spotKey(hs));
    T.log("spot", { lesson: lesson.id, page: state.page + 1, ch: hs.id, first: firstTime });
    updateSpotChip(pageSpots);
    el.classList.add("seen");
    // 已经说上了：再点就重说一遍，不叠动作。
    // 减弱动态模式也照常锄一下——一次性动作是「我点到了」的反馈，
    // 不是持续晃动，停掉它只会让孩子以为没点着。
    if (busyActors.has(el)) {
      showBubble(hs, el);
      playAudio(hs.audio).then(ok => { if (!ok && hs.line) speak(hs.line); });
      return;
    }
    busyActors.add(el);
    const up = el.querySelector(".upper");
    const arm = el.querySelector(".arm");
    const low = el.querySelector(".lower");
    const body = el.querySelector(".body");
    const idle = el._idle;
    const idleArm = el._idleArm;
    const idleLow = el._idleLow;
    try {
      if (idle) idle.pause();
      if (idleArm) idleArm.pause();
      if (idleLow) idleLow.pause();
      // 锄头落进土里那一刻开口，别等整套动作演完——点了半天没反应最劝退
      const act = up ? hoeTwice(up, arm, low) : null;
      if (act) await wait(520);
      else await chop(body, 620).finished.catch(() => {});
      const ms = showBubble(hs, el);
      playAudio(hs.audio).then(ok => {
        if (!ok && hs.line) speak(hs.line);
      });
      await wait(ms + 400);
      if (act) await act;
    } finally {
      if (idle) idle.play();
      if (idleArm) idleArm.play();
      if (idleLow) idleLow.play();
      busyActors.delete(el);
    }
  }

  function showBubble(hs, el) {
    const bubble = document.getElementById("bubble");
    const card = document.querySelector(".scene-card");
    if (!bubble || !card) return;
    bubble.innerHTML = '<b>' + esc(hs.label) + '</b><span>' + esc(hs.line || "") + '</span>';
    bubble.hidden = false;

    const c = card.getBoundingClientRect(), r = el.getBoundingClientRect();
    const bw = bubble.offsetWidth, bh = bubble.offsetHeight, pad = 10;
    // 以圆点（热区中心）为锚，而不是盒子边缘：盒子可能很高，气泡会飘走。
    // 贴纸是一个人，锚点改取他的头顶/脚底，气泡才不会压在他脸上。
    const cx = r.left - c.left + r.width / 2;
    const topY = r.top - c.top, botY = r.bottom - c.top;
    const anchorY = hs.actor ? topY : (topY + botY) / 2;
    const gap = 34;
    const above = hs.actor ? topY - bh - gap : anchorY - bh / 2 - gap;
    const below = hs.actor ? botY + gap : anchorY + bh / 2 + gap;
    let top;
    if (above >= pad) top = above;                                      // 上方放得下就放上面
    else if (below + bh <= c.height - pad) top = below;                 // 放不下就贴到下面
    else top = Math.max(pad, Math.min(c.height - bh - pad, above));
    const left = Math.max(pad, Math.min(c.width - bw - pad, cx - bw / 2));
    bubble.style.left = left + "px";
    bubble.style.top = top + "px";

    // 气泡是当前焦点，进度片先让一让
    const chip = document.getElementById("spotChip");
    if (chip) chip.classList.add("mute");

    clearTimeout(bubbleTimer);
    const ms = Math.min(6500, 1600 + (hs.line || "").length * 260);
    bubbleTimer = setTimeout(hideBubble, ms);
    return ms;
  }

  function hideBubble() {
    clearTimeout(bubbleTimer);
    const bubble = document.getElementById("bubble");
    if (bubble) bubble.hidden = true;
    const chip = document.getElementById("spotChip");
    if (chip) chip.classList.remove("mute");
  }

  /* ---------------- 一屏定版 ---------------- */

  // 图框：在舞台里取最大的 4:3~5:3 矩形。
  // 竖屏舞台偏方，用 5:3 左右；横屏舞台偏竖，退到 4:3，避免把画面裁太狠。
  function fitStage() {
    const stage = document.getElementById("stage");
    const card = stage && stage.querySelector(".scene-card");
    if (!stage || !card) return;
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;
    const ratio = Math.min(5 / 3, Math.max(4 / 3, w / h));
    let cw = w, ch = w / ratio;
    if (ch > h) { ch = h; cw = h * ratio; }
    card.style.width = Math.floor(cw) + "px";
    card.style.height = Math.floor(ch) + "px";
  }

  // 文字实际占的方框（align-content:center 时 scrollHeight 不可靠，直接量子元素）
  function textExtent(box) {
    let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
    box.querySelectorAll("button.ch,.punct").forEach(p => {
      const r = p.getBoundingClientRect();
      if (!r.width) return;
      top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom);
      left = Math.min(left, r.left); right = Math.max(right, r.right);
    });
    if (!isFinite(top)) return null;
    return { w: right - left, h: bottom - top };
  }

  function fits(box, w, h) {
    const e = textExtent(box);
    if (!e) return true;
    // 宽度放宽 1px：长句自动折行后会正好铺满整行，那不是溢出
    return e.w <= w + 1 && e.h <= h - 10 && box.scrollWidth <= w + 1;
  }

  // 字号：二分出「宽度和高度都放得下」的最大值，再往下留一点余量
  // 字号：同一本书所有页共用一个字号。
  // 以前是逐页求最大值 —— 短短一句会撑到 130px，下一句 20 字立刻缩到 60px，
  // 翻页时字号一跳，孩子的眼睛要重新对焦，认字的视觉经验也断了。
  // 现在取「本书最长的一页能放下的最大字号」，全书统一。
  let fsCache = { key: "", fs: 0 };

  function maxFsFor(box, w, h, cap) {
    box.style.setProperty("--fs", cap + "px");
    if (fits(box, w, h)) return cap;
    let lo = 13, hi = cap;
    for (let i = 0; i < 14; i++) {
      const mid = (lo + hi) / 2;
      box.style.setProperty("--fs", mid + "px");
      if (fits(box, w, h)) lo = mid; else hi = mid;
    }
    return Math.floor(lo * 10) / 10;
  }

  function bookFontSize(lesson, w, h) {
    const key = lesson.id + "|" + w + "x" + h;
    if (fsCache.key === key) return fsCache.fs;

    // 找出字数最多的一页做起点（多数情况下它就是最难排的）
    let worst = lesson.pages[0].text, wn = charsOf(worst).length;
    for (const pg of lesson.pages) {
      const n = charsOf(pg.text).length;
      if (n > wn) { wn = n; worst = pg.text; }
    }

    // 离屏量：真 #textline 上的按钮已经绑了事件，不能替换它的内容
    const probe = document.createElement("div");
    probe.className = "textline";
    probe.setAttribute("aria-hidden", "true");
    probe.style.cssText =
      "position:fixed;left:-9999px;top:0;visibility:hidden;pointer-events:none;" +
      "display:flex;flex-direction:column;justify-content:center;text-align:left;" +
      "width:" + w + "px;height:" + h + "px;";
    document.body.appendChild(probe);

    const cap = Math.min(wn <= 8 ? h * 0.6 : h * 0.28, wn <= 8 ? 130 : 104);
    probe.innerHTML = phrasesMarkup(worst);
    let fs = maxFsFor(probe, w, h, cap);

    // 字数最多不等于最难排：断行落点不同，别的页也可能更挤。
    // 逐页校一遍，谁放不下就把全书字号压到它能放下 —— 宁可小幅牺牲，也要全书一致。
    for (const pg of lesson.pages) {
      probe.innerHTML = phrasesMarkup(pg.text);
      probe.style.setProperty("--fs", fs + "px");
      if (!fits(probe, w, h)) fs = maxFsFor(probe, w, h, fs);
    }

    probe.remove();

    // 取满格会顶到卡片边，一行只剩四五个字，翻页时像在挤牙膏。
    // 留一成余量，相当于按每页 23 个字来定，行宽和留白都舒服。
    fs = Math.floor(fs * 0.88 * 10) / 10;

    // 一行至少要放得下 6 个字。横屏文字列只有 46% 宽，0.88 的余量仍然会让
    // 一行掉到四五个字（「农夫跑过 / 去，捡起兔」），左对齐之后看着更碎。
    // 竖屏本来就有一行 7 个字，这一条碰不到它。
    fs = Math.min(fs, Math.floor((w / 6.4) * 10) / 10);

    fsCache = { key: key, fs: fs };
    return fs;
  }

  function fitText() {
    const box = document.getElementById("textline");
    if (!box) return;
    const w = box.clientWidth, h = box.clientHeight;
    if (!w || !h) return;

    const lesson = current();
    if (!lesson || lesson.kind !== "story" || !lesson.pages) return;

    const fs = bookFontSize(lesson, w, h);
    box.style.setProperty("--fs", fs + "px");

    // 兜底：万一某页标点特别密仍然放不下，只收这一页，不改全书字号
    if (!fits(box, w, h)) {
      let lo = 13, hi = fs;
      for (let i = 0; i < 12; i++) {
        const mid = (lo + hi) / 2;
        box.style.setProperty("--fs", mid + "px");
        if (fits(box, w, h)) lo = mid; else hi = mid;
      }
      box.style.setProperty("--fs", Math.floor(lo * 10) / 10 + "px");
    }
  }

  // 图板：插画被 object-fit:cover 之后的真实矩形。宽高都按 cover 算，
  // 位置跟着 object-position:center 46% 走，和 CSS 里那条规则一致。
  // 贴纸、热点都按原图百分比挂在这块板上，所以转屏时只要挪动图板本身。
  function layoutPlate() {
    const card = document.querySelector(".scene-card");
    const img = document.querySelector("#scene img.art");
    const plate = document.getElementById("plate");
    if (!card || !img || !plate) return;
    const iw = img.naturalWidth, ih = img.naturalHeight;
    const cw = card.clientWidth, ch = card.clientHeight;
    if (!iw || !ih || !cw || !ch) return;
    const s = Math.max(cw / iw, ch / ih);
    const dw = iw * s, dh = ih * s;
    plate.style.width = dw + "px";
    plate.style.height = dh + "px";
    plate.style.left = (cw - dw) * 0.5 + "px";
    plate.style.top = (ch - dh) * 0.46 + "px";
  }

  function relayout() {
    fitStage();
    fitText();
    layoutPlate();
  }

  let fitTimer = null;
  function scheduleFit(delay) {
    clearTimeout(fitTimer);
    fitTimer = setTimeout(relayout, delay == null ? 120 : delay);
  }

  window.addEventListener("resize", () => scheduleFit(120));
  window.addEventListener("orientationchange", () => {
    scheduleFit(60);
    setTimeout(relayout, 320);   // iOS 转屏后尺寸会晚一拍才稳定
  });
  if (window.visualViewport) window.visualViewport.addEventListener("resize", () => scheduleFit(120));
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => relayout());

  function renderCards(lesson) {
    const cards = lesson.cards || [];
    view.innerHTML =
      '<section class="cards">' +
        '<div class="cards-head"><h2>先认这 ' + cards.length + ' 个字</h2><p>轻点听音 · 长按看大字</p></div>' +
        '<div class="grid">' + cards.map(c => {
          const m = S.chars[c.ch] || {};
          return '<div class="card" data-ch="' + c.ch + '" role="button" tabindex="0" aria-label="' + c.ch + '">' +
            '<div class="glyph">' + c.ch + '</div>' +
            '<div class="py">' + esc(m.pinyin || "") + '</div>' +
            '<button class="wordbtn" data-word="' + esc(m.word || "") + '" data-ch="' + c.ch + '">' + esc(m.word || "") + '</button>' +
          '</div>';
        }).join("") + '</div>' +
      '</section>';

    document.querySelectorAll(".card").forEach(el => {
      const ch = el.dataset.ch;
      bindPress(el, () => tapChar(ch, el), () => showBig(ch));
    });
    document.querySelectorAll(".wordbtn").forEach(btn => {
      btn.addEventListener("pointerdown", e => e.stopPropagation());
      btn.addEventListener("click", e => { e.stopPropagation(); tapWord(btn.dataset.word, btn.dataset.ch); });
    });

    logExposure(0);
    preload(cards.map(c => audioFor(c.ch).audio).concat(cards.map(c => audioFor(c.ch).wordAudio)));
  }

  function goPage(i) {
    const lesson = current();
    if (i < 0 || i >= lesson.pages.length || i === state.page) return;
    state.page = i;
    stopAudio();
    render();
  }

  function turn(d) { goPage(state.page + d); }

  /* ---------------- 读一遍 ---------------- */

  function readAll() {
    const lesson = current();
    const page = lesson.pages[state.page];
    const btn = document.getElementById("readall");
    const chEls = Array.from(document.querySelectorAll("#textline .ch"));
    if (!btn) return;

    T.log("read", { lesson: lesson.id, page: state.page + 1 });
    btn.classList.add("playing");

    const finish = () => {
      btn.classList.remove("playing");
      chEls.forEach(el => el.classList.remove("lit"));
    };

    playAudio(page.audio).then(ok => {
      if (!ok) {
        // 没有整页音频就一个字一个字读，仍然不计点击
        let i = 0;
        const step = () => {
          if (i >= chEls.length) return finish();
          const el = chEls[i++];
          el.classList.add("lit");
          const m = audioFor(el.dataset.ch);
          const a = m.audio ? getAudio(m.audio) : null;
          if (a) {
            a.onended = () => { el.classList.remove("lit"); step(); };
            a.currentTime = 0;
            a.play().catch(() => { el.classList.remove("lit"); step(); });
          } else {
            setTimeout(() => { el.classList.remove("lit"); step(); }, 600);
          }
        };
        step();
        return;
      }

      const a = state.playing || getAudio(page.audio);
      const n = chEls.length;
      const update = () => {
        if (state.playing !== a) { a.removeEventListener("timeupdate", update); return; }
        if (!a.duration || !isFinite(a.duration)) return;
        const idx = Math.min(n - 1, Math.floor((a.currentTime / a.duration) * n));
        chEls.forEach((el, i) => el.classList.toggle("lit", i <= idx));
      };
      a.addEventListener("timeupdate", update);
      a.addEventListener("ended", () => {
        a.removeEventListener("timeupdate", update);
        finish();
      }, { once: true });
      setTimeout(() => { if (a.paused) finish(); }, 100);
    });
  }

  /* ---------------- 家长面板 ---------------- */

  const JC = {
    "会（家长）": "j-know",
    "不会（家长）": "j-not",
    "测验未过": "j-quiz",
    "反复点": "j-repeat",
    "新鲜感": "j-new",
    "?（家长）": "j-none",
    "没看到": "j-none",
    "从不点": "j-none",
    "待观察": "j-none",
  };

  function renderDrawer() {
    const { rows, summary } = T.stats(S.lessons, S.chars);
    const lat = summary.latency == null ? "—" : summary.latency + "ms";
    drawerSub.textContent = S.lessons.length + " 节课 · " + summary.totalChars + " 个字 · 事件只存在这台设备";

    drawerBody.innerHTML =
      '<div class="summary">' +
        '<span>看过 <b>' + summary.seenChars + "/" + summary.totalChars + '</b> 字</span>' +
        '<span><b>' + summary.sessions + '</b> 次会话</span>' +
        '<span><b>' + summary.todayTaps + '</b> 今日点读</span>' +
        '<span>延迟中位数 <b>' + lat + '</b></span>' +
      '</div>' +
      (summary.events === 0 ? '<p class="note">还没有数据。让孩子读一页，这里就会出现每个字的曝光和点读。</p>' : '') +
      '<table class="stat"><thead><tr>' +
        '<th>字</th><th>出现</th><th>点了</th><th>率</th><th>跨天</th><th>单次</th><th>判断</th><th>标注</th>' +
      '</tr></thead><tbody>' +
      rows.map(r => {
        const rate = r.exp ? r.rate.toFixed(1) : "—";
        return '<tr>' +
          '<td class="c-ch">' + r.ch + '<i>' + esc(r.pinyin) + '</i></td>' +
          '<td>' + r.exp + '</td>' +
          '<td>' + r.taps + '</td>' +
          '<td>' + rate + '</td>' +
          '<td>' + r.days + '</td>' +
          '<td>' + r.maxSingle + '</td>' +
          '<td><span class="judge ' + (JC[r.judge] || "j-none") + '">' + r.judge + '</span></td>' +
          '<td class="labels">' +
            '<button class="lab' + (r.label === "know" ? " on" : "") + '" data-ch="' + r.ch + '" data-l="know">会</button>' +
            '<button class="lab not' + (r.label === "not" ? " on" : "") + '" data-ch="' + r.ch + '" data-l="not">不会</button>' +
            '<button class="lab' + (r.label === "q" ? " on" : "") + '" data-ch="' + r.ch + '" data-l="q">?</button>' +
          '</td>' +
        '</tr>';
      }).join("") +
      '</tbody></table>';

    drawerBody.querySelectorAll(".lab").forEach(btn => {
      btn.addEventListener("click", () => {
        const ch = btn.dataset.ch;
        const cur = T.labels()[ch];
        T.setLabel(ch, cur === btn.dataset.l ? "" : btn.dataset.l);
        renderDrawer();
      });
    });
  }

  function openDrawer() {
    renderDrawer();
    mask.hidden = false;
    drawer.classList.add("on");
    drawer.setAttribute("aria-hidden", "false");
  }

  function closeDrawer() {
    drawer.classList.remove("on");
    drawer.setAttribute("aria-hidden", "true");
    setTimeout(() => { mask.hidden = true; }, 200);
  }

  function updateFoot() {
    if (!footStat) return;
    const { summary } = T.stats(S.lessons, S.chars);
    footStat.textContent = summary.totalChars + " 个字 · 读过 " + summary.seenChars;
  }

  /* ---------------- 听音找字 ---------------- */

  const shuffle = arr => arr.map(v => [Math.random(), v]).sort((a, b) => a[0] - b[0]).map(x => x[1]);

  function startQuiz() {
    const { rows } = T.stats(S.lessons, S.chars);
    let pool = rows.filter(r => r.exp > 0).map(r => r.ch);
    if (pool.length < 4) pool = rows.map(r => r.ch);
    if (pool.length < 4) return;

    const leftover = quizWrap.querySelector(".primary-btn");
    if (leftover) leftover.remove();
    const list = shuffle(pool).slice(0, Math.min(5, pool.length));
    state.quiz = { list, i: 0, score: 0, locked: false };
    closeDrawer();
    quizWrap.hidden = false;
    requestAnimationFrame(() => quizWrap.classList.add("on"));
    askQuestion();
  }

  function askQuestion() {
    const q = state.quiz;
    if (!q) return;
    if (q.i >= q.list.length) return finishQuiz();

    q.locked = false;
    const ch = q.list[q.i];
    const others = shuffle(Object.keys(S.chars).filter(c => c !== ch)).slice(0, 3);
    const opts = shuffle([ch].concat(others));

    quizCount.textContent = (q.i + 1) + " / " + q.list.length;
    quizMsg.textContent = "";
    optionsEl.innerHTML = opts.map(c => '<button class="option" data-ch="' + c + '">' + c + '</button>').join("");
    optionsEl.querySelectorAll(".option").forEach(btn => {
      btn.addEventListener("click", () => answer(btn.dataset.ch, btn));
    });
    replayBtn.hidden = false;
    replayBtn.onclick = () => playAudio(audioFor(ch).audio);
    setTimeout(() => playAudio(audioFor(ch).audio), 280);
  }

  function answer(ch, btn) {
    const q = state.quiz;
    if (!q || q.locked) return;
    q.locked = true;

    const target = q.list[q.i];
    const ok = ch === target;
    T.log("quiz", { lesson: current().id, page: 0, ch: target, ok });

    optionsEl.querySelectorAll(".option").forEach(b => {
      b.disabled = true;
      if (b.dataset.ch === target) b.classList.add("correct");
    });
    if (!ok) btn.classList.add("wrong");
    else q.score += 1;

    quizMsg.textContent = ok ? "对了，就是这个字" : "再听一次：" + target;
    setTimeout(() => { q.i += 1; askQuestion(); }, ok ? 720 : 1250);
  }

  function finishQuiz() {
    const q = state.quiz;
    const n = q.list.length;
    const score = q.score;
    quizCount.textContent = "完成";
    replayBtn.hidden = true;
    optionsEl.innerHTML =
      '<div class="result" style="grid-column:1/-1;padding:14px 4px 6px">' +
        '<div style="font-size:44px;line-height:1.2">' + (score === n ? "全对" : score >= n - 1 ? "很好" : "再试试") + '</div>' +
        '<div style="color:#8B8172;font-size:14px;margin-top:6px">答对 ' + score + ' / ' + n + ' 个</div>' +
      '</div>';
    quizMsg.textContent = "";
    const again = document.createElement("button");
    again.className = "primary-btn";
    again.textContent = "再来一次";
    again.style.marginTop = "14px";
    again.addEventListener("click", startQuiz);
    optionsEl.after(again);
    state.quiz = null;
    updateFoot();
  }

  function closeQuiz() {
    state.quiz = null;
    quizWrap.classList.remove("on");
    setTimeout(() => { quizWrap.hidden = true; }, 200);
    const extra = quizWrap.querySelector(".primary-btn");
    if (extra) extra.remove();
  }

  /* ---------------- 导出 / 清空 ---------------- */

  function testSound() {
    const ch = Object.keys(S.chars)[0];
    const src = S.chars[ch] && S.chars[ch].audio;
    if (!src) { toast("没有可用的音频"); return; }
    playAudio(src, lat => toast("声音正常 · " + lat + "ms")).then(ok => {
      if (!ok) toast("这台设备没有放出声音：检查音量，或换浏览器打开");
    });
  }

  // 家长问「怎么不动」时，这一下能分清是设备设置还是页面本身
  function testMotion() {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const el = document.querySelector(".actor");
    const up = el && el.querySelector(".upper");
    const arm = el && el.querySelector(".arm");
    const body = el && el.querySelector(".body");
    if (up) {
      // 有关节的角色就演一遍真的锄地，比整体压弹更能说明问题
      swingOnce(up, arm, -7.4, -12.4, 1100);
    } else if (body) {
      body.animate([
        { transform: "translateY(0) scaleY(1)" },
        { transform: "translateY(2.5%) scaleY(.93)", offset: .18 },
        { transform: "translateY(-2.5%) scaleY(1.06)", offset: .55 },
        { transform: "translateY(0) scaleY(1)" }
      ], { duration: 1500, easing: "ease-in-out" });
    }
    const none = body ? "" : "（这页没有会动的人物，翻到故事页再试）";
    toast(reduced
      ? "系统开着「减弱动态效果」，动画被降到最轻" + none
      : "动画正常：画面在缓慢推近，农夫在锄地" + none);
  }

  function exportData() {
    const data = T.exportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    const d = new Date();
    const p = n => String(n).padStart(2, "0");
    a.href = URL.createObjectURL(blob);
    a.download = "shizi-events-" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  function resetAll() {
    if (!confirm("清空这台设备上的所有学习记录？导出过的文件不受影响。")) return;
    T.reset();
    T.init();
    state.expSeen.clear();
    renderDrawer();
    updateFoot();
  }

  /* ---------------- 事件绑定 ---------------- */

  document.getElementById("parentBtn").addEventListener("click", openDrawer);
  document.getElementById("closeDrawer").addEventListener("click", closeDrawer);
  document.getElementById("mask").addEventListener("click", closeDrawer);
  document.getElementById("quizBtn").addEventListener("click", startQuiz);
  document.getElementById("exportBtn").addEventListener("click", exportData);
  document.getElementById("soundBtn").addEventListener("click", testSound);
  document.getElementById("motionBtn").addEventListener("click", testMotion);
  document.getElementById("resetBtn").addEventListener("click", resetAll);
  document.getElementById("closeQuiz").addEventListener("click", closeQuiz);
  picker.addEventListener("click", () => {
    if (pickerWrap.hidden) openPicker(); else closePicker();
  });
  pwClose.addEventListener("click", closePicker);
  pwScrim.addEventListener("click", closePicker);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !pickerWrap.hidden) closePicker();
  });
  bigCard.addEventListener("click", e => { e.stopPropagation(); if (swallowBigClick) return; toggleBig(); });
  bigWrap.addEventListener("click", () => { if (swallowBigClick) return; hideBig(); });
  document.addEventListener("pointerdown", () => { swallowBigClick = false; }, true);

  /* ---------------- 防误触：整页不滚、不缩放 ---------------- */

  // 页内没有可滚的地方，touchmove 一律吃掉，顺手挡掉 iOS 的橡皮筋和下拉刷新。
  // 只有家长面板和测验弹窗需要滚，那两个区域放行。
  const scrollable = el => !!(el && el.closest && el.closest(".drawer-body,.quizcard"));
  document.addEventListener("touchmove", e => {
    if (scrollable(e.target)) return;
    if (e.cancelable) e.preventDefault();
  }, { passive: false });
  document.addEventListener("gesturestart", e => e.preventDefault());   // iOS 双指缩放
  document.addEventListener("gesturechange", e => e.preventDefault());

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      if (!bigWrap.hidden) hideBig();
      else if (!quizWrap.hidden) closeQuiz();
      else if (drawer.classList.contains("on")) closeDrawer();
    }
    if (!quizWrap.hidden && state.quiz) {
      const n = Number(e.key);
      if (n >= 1 && n <= 4) {
        const btn = optionsEl.querySelectorAll(".option")[n - 1];
        if (btn && !btn.disabled) btn.click();
      }
    }
  });

  /* ---------------- 启动 ---------------- */

  function boot() {
    T.init();
    if (!S || !S.lessons || !S.lessons.length) {
      view.innerHTML = '<p style="text-align:center;color:#8B8172">还没有课程，先运行 pipeline/build.py</p>';
      return;
    }
    let start = null;
    try {
      const raw = localStorage.getItem("shizi.last");
      if (raw !== null) {
        const last = Number(raw);
        if (Number.isInteger(last) && last >= 0 && last < S.lessons.length) start = last;
      }
    } catch (e) { /* noop */ }
    if (start == null) {
      const story = S.lessons.findIndex(l => l.kind === "story");
      start = story >= 0 ? story : 0;
    }
    state.lesson = start;
    renderPicker();
    render();
  }

  boot();
})();
