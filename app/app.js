/* 儿童端主逻辑：点读、长按大字、翻页、家长面板、听音找字。 */
(function () {
  const S = window.SHIZI;
  const T = window.ShiziTrack;
  const HANZI = /[\u4e00-\u9fff]/;

  const view = document.getElementById("view");
  const tabsEl = document.getElementById("tabs");
  const subtitle = document.getElementById("subtitle");
  const footHint = document.getElementById("footHint");
  const footStat = document.getElementById("footStat");

  const mask = document.getElementById("mask");
  const drawer = document.getElementById("drawer");
  const drawerSub = document.getElementById("drawerSub");
  const drawerBody = document.getElementById("drawerBody");

  const bigWrap = document.getElementById("bigWrap");
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
    bigTimer: null,
    quiz: null,
    flash: new Map(),
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

  function bindPress(el, onTap, onLong) {
    let timer = null, sx = 0, sy = 0, fired = false, down = false;

    const clear = () => { if (timer) { clearTimeout(timer); timer = null; } };
    const cancel = () => { down = false; clear(); el.classList.remove("press"); };

    el.addEventListener("pointerdown", e => {
      if (e.button != null && e.button > 0) return;
      down = true; fired = false; sx = e.clientX; sy = e.clientY;
      el.classList.add("press");
      clear();
      timer = setTimeout(() => {
        fired = true; down = false; timer = null;
        el.classList.remove("press");
        if (onLong) onLong();
      }, 420);
    });

    el.addEventListener("pointermove", e => {
      if (!down) return;
      if (Math.abs(e.clientX - sx) > 10 || Math.abs(e.clientY - sy) > 10) cancel();
    });

    el.addEventListener("pointerup", () => {
      if (!down) return;
      down = false; clear(); el.classList.remove("press");
      if (!fired) onTap();
    });

    el.addEventListener("pointercancel", cancel);
    el.addEventListener("pointerleave", cancel);
    el.addEventListener("contextmenu", e => e.preventDefault());

    el.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (onTap) onTap();
      }
    });
  }

  /* ---------------- 点读 ---------------- */

  function flash(ch) {
    const prev = state.flash.get(ch);
    if (prev) prev.forEach(el => el.classList.remove("lit", "active"));

    const lit = Array.from(document.querySelectorAll('button.ch[data-ch="' + ch + '"]'));
    const spots = Array.from(document.querySelectorAll('.spot[data-ch="' + ch + '"]'));
    lit.forEach(el => el.classList.add("lit"));
    spots.forEach(el => el.classList.add("active"));
    state.flash.set(ch, lit.concat(spots));

    setTimeout(() => {
      lit.forEach(el => el.classList.remove("lit"));
      spots.forEach(el => el.classList.remove("active"));
      state.flash.delete(ch);
    }, 1200);
  }

  function tapChar(ch) {
    const lesson = current();
    const readBtn = document.getElementById("readall");
    if (readBtn) readBtn.classList.remove("playing");
    const meta = audioFor(ch);
    flash(ch);
    playAudio(meta.audio, lat => {
      T.log("tap", { lesson: lesson.id, page: pageNo(), ch, lat });
      updateFoot();
    }).then(ok => {
      if (!ok) {
        speak(ch);
        T.log("tap", { lesson: lesson.id, page: pageNo(), ch, lat: null });
        updateFoot();
        toast("这一段没播出声音", () => tapChar(ch));
      }
    });
  }

  function tapWord(word, ch) {
    const meta = audioFor(ch);
    if (meta.wordAudio) playAudio(meta.wordAudio);
    T.log("word", { lesson: current().id, page: pageNo(), ch });
  }

  function showBig(ch) {
    const meta = audioFor(ch);
    if (!meta.pinyin) return;
    T.log("long", { lesson: current().id, page: pageNo(), ch });
    bigGlyph.textContent = ch;
    bigPy.textContent = meta.pinyin || "";
    bigWord.textContent = meta.word || "";
    bigWrap.hidden = false;
    requestAnimationFrame(() => bigWrap.classList.add("on"));
    clearTimeout(state.bigTimer);
    state.bigTimer = setTimeout(hideBig, 1800);
  }

  function hideBig() {
    clearTimeout(state.bigTimer);
    bigWrap.classList.remove("on");
    setTimeout(() => { bigWrap.hidden = true; }, 180);
  }

  /* ---------------- 课程渲染 ---------------- */

  function shortTitle(l) {
    if (l.kind === "cards") return (l.cards || []).map(c => c.ch).join(" ");
    return l.title;
  }

  function renderTabs() {
    tabsEl.innerHTML = S.lessons.map((l, i) =>
      '<button class="tab' + (i === state.lesson ? " on" : "") + '" data-i="' + i + '" role="tab" aria-selected="' + (i === state.lesson) + '">' +
        '<span class="tabnum">' + (i + 1) + '</span>' +
        '<span class="tname">' +
          (l.kind === "cards"
            ? '<span class="wide">' + esc(shortTitle(l)) + '</span><span class="narrow">字卡</span>'
            : esc(shortTitle(l))) +
        '</span>' +
      '</button>'
    ).join("");
    tabsEl.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => selectLesson(Number(btn.dataset.i)));
    });
  }

  function selectLesson(i) {
    state.lesson = i;
    state.page = 0;
    renderTabs();
    render();
    try { localStorage.setItem("shizi.last", String(i)); } catch (e) { /* noop */ }
  }

  function render() {
    const lesson = current();
    subtitle.textContent = lesson.kind === "cards" ? "先认这几个字" : "点字听声音";
    footHint.textContent = lesson.kind === "cards" ? "轻点听音 · 长按看大字" : "轻点字听声音 · 长按看大字";
    if (lesson.kind === "cards") renderCards(lesson); else renderStory(lesson);
    updateFoot();
  }

  function renderStory(lesson) {
    const page = lesson.pages[state.page];
    const phrasesHtml = phrases(page.text).map(ph => {
      const inner = Array.from(ph).map(ch => {
        if (!HANZI.test(ch)) return '<span class="punct">' + esc(ch) + '</span>';
        return '<button class="ch" data-ch="' + ch + '" aria-label="' + ch + '">' + ch + '</button>';
      }).join("");
      return '<span class="phrase">' + inner + '</span>';
    }).join("");

    const art = page.art && page.art.file;
    const sceneHtml = art
      ? '<img class="art" src="' + esc(art) + '" alt="" draggable="false">'
      : window.renderScene(page.scene, { spots: false });

    view.innerHTML =
      '<section class="story">' +
        '<div class="scene-card">' +
          '<div class="scene" id="scene">' + sceneHtml + '</div>' +
          '<button class="nav prev" id="prev" aria-label="上一页"' + (state.page === 0 ? " disabled" : "") + '>‹</button>' +
          '<button class="nav next" id="next" aria-label="下一页"' + (state.page === lesson.pages.length - 1 ? " disabled" : "") + '>›</button>' +
        '</div>' +
        '<div class="textcard">' +
          '<div class="pageno">' + (state.page + 1) + " / " + lesson.pages.length + '</div>' +
          '<div class="textline" id="textline">' + phrasesHtml + '</div>' +
          '<div class="pager" id="pager">' + lesson.pages.map((_, i) =>
            '<button class="dot' + (i === state.page ? " on" : "") + '" data-p="' + i + '" aria-label="第 ' + (i + 1) + ' 页"></button>'
          ).join("") + '</div>' +
        '</div>' +
        '<div class="storybar"><button class="readall" id="readall">' +
          '<svg class="spk" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4Z" fill="currentColor"/></svg>读一遍</button></div>' +
      '</section>';

    document.querySelectorAll("#textline .ch").forEach(el => {
      const ch = el.dataset.ch;
      bindPress(el, () => tapChar(ch), () => showBig(ch));
    });

    document.getElementById("prev").addEventListener("click", () => turn(-1));
    document.getElementById("next").addEventListener("click", () => turn(1));
    document.querySelectorAll(".dot").forEach(d => {
      d.addEventListener("click", () => goPage(Number(d.dataset.p)));
    });
    document.getElementById("readall").addEventListener("click", readAll);

    logExposure(state.page + 1);
    preload([page.audio].concat(charsOf(page.text).map(ch => audioFor(ch).audio)));
  }

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
      bindPress(el, () => tapChar(ch), () => showBig(ch));
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
  bigWrap.addEventListener("click", hideBig);

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
    renderTabs();
    render();
  }

  boot();
})();
