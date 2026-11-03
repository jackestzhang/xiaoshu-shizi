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
    return (page.hotspots || []).filter(hs => hs.actor).map(hs =>
      '<button class="actor" data-id="' + esc(hs.id) + '" aria-label="' + esc(hs.label) + '"' +
        ' style="left:' + round2(hs.x - hs.w / 2) + '%;top:' + round2(hs.y - hs.h / 2) +
        '%;width:' + round2(hs.w) + '%">' +
        '<span class="body">' +
          '<img class="skin" src="' + esc(hs.actor) + '" alt="" draggable="false">' +
        '</span>' +
      '</button>').join("");
  }

  const round2 = v => Math.round(v * 100) / 100;

  function paintSpots(page) {
    const wrap = document.getElementById("spots");
    const list = (page.hotspots || []).filter(hs => !hs.actor);
    if (!wrap) return;
    wrap.innerHTML = "";
    list.forEach(hs => {
      const b = document.createElement("button");
      b.className = "spot" + (spotsSeen.has(spotKey(hs)) ? " seen" : "");
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
      wrap.appendChild(b);
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

  function startIdle(el) {
    if (reduceMotion.matches) return;
    const body = el.querySelector(".body");
    if (!body) return;
    el._idle = body.animate([
      { transform: "translateY(0) scaleY(1)" },
      { transform: "translateY(-0.35%) scaleY(1.012)", offset: .5 },
      { transform: "translateY(0) scaleY(1)" }
    ], { duration: 4200, iterations: Infinity, easing: "ease-in-out" });
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

  async function tapActor(hs, el) {
    const lesson = current();
    const pageSpots = lesson.pages[state.page].hotspots || [];
    const firstTime = !spotsSeen.has(spotKey(hs));
    spotsSeen.add(spotKey(hs));
    T.log("spot", { lesson: lesson.id, page: state.page + 1, ch: hs.id, first: firstTime });
    updateSpotChip(pageSpots);
    el.classList.add("seen");
    // 已经说上了：再点就重说一遍，不叠动作
    if (busyActors.has(el) || reduceMotion.matches) {
      showBubble(hs, el);
      playAudio(hs.audio).then(ok => { if (!ok && hs.line) speak(hs.line); });
      return;
    }
    busyActors.add(el);
    const body = el.querySelector(".body");
    const idle = el._idle;
    try {
      if (idle) idle.pause();
      const hit = chop(body, 620);            // 锄一下，再直起腰
      await hit.finished.catch(() => {});
      const ms = showBubble(hs, el);
      playAudio(hs.audio).then(ok => {
        if (!ok && hs.line) speak(hs.line);
      });
      await wait(ms + 400);
      hit.cancel();
    } finally {
      if (idle) idle.play();
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
