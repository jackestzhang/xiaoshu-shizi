/* 事件层：只存原始事件，指标全部现算。
 *
 * 为什么不用聚合值：口径已经改过几次（整课曝光 → 按页曝光、读一遍不计点击、
 * 面板只读、50ms 撤回）。聚合一旦落盘，旧数据就再也算不成新口径。
 *
 * 同一份逻辑在 pipeline/report.py 里有一份镜像，tests/parity.js 会逐字比对。
 */
(function (root) {
  const EVENTS_KEY = "shizi.events.v1";
  const LABELS_KEY = "shizi.labels.v1";
  const VERSION = 1;

  const mem = { events: [], labels: {} };
  const hasLS = (() => {
    try { return typeof localStorage !== "undefined" && !!localStorage; } catch (e) { return false; }
  })();

  function read(key, fallback) {
    if (!hasLS) return fallback;
    try {
      const raw = localStorage.getItem(key);
      // 本机被清空时必须以存储为准，不能回落到内存里的旧数组
      if (raw == null) return Array.isArray(fallback) ? [] : {};
      return JSON.parse(raw);
    } catch (e) { return fallback; }
  }

  function write(key, val) {
    if (hasLS) {
      try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* 满了就算了 */ }
    }
  }

  function dayOf(ts) {
    const d = new Date(ts);
    const p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  let sid = null;
  let startedAt = 0;
  let ended = false;

  function init() {
    if (sid) return sid;
    sid = "s-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 6);
    startedAt = Date.now();
    ended = false;
    log("start", {});
    const end = () => {
      if (ended) return;
      ended = true;
      log("end", { dur: Date.now() - startedAt });
    };
    if (typeof window !== "undefined") {
      window.addEventListener("pagehide", end);
      document.addEventListener("visibilitychange", () => { if (document.hidden) end(); });
    }
    return sid;
  }

  function log(kind, data) {
    const e = Object.assign({ kind, ts: Date.now(), sid: sid || "s-anon", day: dayOf(Date.now()) }, data || {});
    const all = read(EVENTS_KEY, mem.events);
    all.push(e);
    if (all.length > 4000) all.splice(0, all.length - 4000);
    mem.events = all;
    write(EVENTS_KEY, all);
    return e;
  }

  function events() {
    return read(EVENTS_KEY, mem.events);
  }

  function labels() {
    return read(LABELS_KEY, mem.labels);
  }

  function setLabel(ch, value) {
    const l = labels();
    if (!value) delete l[ch]; else l[ch] = value;
    mem.labels = l;
    write(LABELS_KEY, l);
  }

  function reset() {
    mem.events = [];
    mem.labels = {};
    write(EVENTS_KEY, []);
    write(LABELS_KEY, {});
    // 清空后当前会话作废，避免 pagehide 再补一条孤儿 end 事件
    sid = null;
    ended = true;
  }

  function allChars(lessons) {
    const seen = new Set();
    (lessons || []).forEach(l => {
      if (l.kind === "cards") (l.cards || []).forEach(c => seen.add(c.ch));
      else (l.pages || []).forEach(p => {
        (p.text || "").replace(/[^\u4e00-\u9fff]/g, "").split("").forEach(ch => seen.add(ch));
      });
    });
    return Array.from(seen);
  }

  function stats(lessons, charMeta, labelMap, eventList) {
    const all = eventList || events();
    const labs = labelMap || labels();

    // 撤回灌水曝光：停留 <50ms 且一次都没点的会话
    const sess = {};
    all.forEach(e => {
      if (!sess[e.sid]) sess[e.sid] = { dur: null, taps: 0 };
      if (e.kind === "end") sess[e.sid].dur = e.dur;
      if (e.kind === "tap") sess[e.sid].taps += 1;
    });
    const bad = new Set(Object.keys(sess).filter(s => sess[s].dur != null && sess[s].dur < 50 && sess[s].taps === 0));
    const kept = all.filter(e => !(e.kind === "exp" && bad.has(e.sid)));

    const chars = allChars(lessons);
    const map = {};
    chars.forEach(ch => {
      map[ch] = { ch, exp: 0, taps: 0, days: new Set(), perSid: {}, quizN: 0, quizOK: 0, last: 0 };
    });
    const lats = [];

    kept.forEach(e => {
      if (!e.ch || !map[e.ch]) return;
      const m = map[e.ch];
      if (e.kind === "exp") m.exp += 1;
      if (e.kind === "tap") {
        m.taps += 1;
        m.perSid[e.sid] = (m.perSid[e.sid] || 0) + 1;
        if (typeof e.lat === "number") lats.push(e.lat);
      }
      if (e.kind === "quiz") {
        m.quizN += 1;
        if (e.ok) m.quizOK += 1;
      }
      if (e.day) m.days.add(e.day);
      if (e.ts > m.last) m.last = e.ts;
    });

    const rows = chars.map(ch => {
      const m = map[ch];
      const rate = m.exp ? m.taps / m.exp : 0;
      const days = m.days.size;
      const maxSingle = Math.max(0, ...Object.values(m.perSid));
      const acc = m.quizN ? m.quizOK / m.quizN : null;
      const label = labs[ch] || "";
      let judge;
      if (label === "know") judge = "会（家长）";
      else if (label === "not") judge = "不会（家长）";
      else if (label === "q") judge = "?（家长）";
      else if (m.quizN >= 2 && acc < 0.6) judge = "测验未过";
      else if (days >= 2 && rate >= 0.6) judge = "反复点";
      else if (maxSingle >= 3 && days <= 1) judge = "新鲜感";
      else if (m.exp === 0) judge = "没看到";
      else if (m.taps === 0 && m.exp >= 3) judge = "从不点";
      else judge = "待观察";

      return {
        ch, exp: m.exp, taps: m.taps, rate: Math.round(rate * 10000) / 10000, days, maxSingle,
        quizN: m.quizN, quizOK: m.quizOK, acc: acc == null ? null : Math.round(acc * 10000) / 10000, judge, label,
        pinyin: (charMeta && charMeta[ch] && charMeta[ch].pinyin) || "",
        word: (charMeta && charMeta[ch] && charMeta[ch].word) || "",
      };
    });

    const rank = { "不会（家长）": 0, "测验未过": 1, "反复点": 2, "?（家长）": 3, "新鲜感": 4, "待观察": 5, "从不点": 6, "没看到": 7, "会（家长）": 8 };
    rows.sort((a, b) => (rank[a.judge] - rank[b.judge]) || (b.taps - a.taps) || (a.ch < b.ch ? -1 : a.ch > b.ch ? 1 : 0));

    const seen = rows.filter(r => r.exp > 0).length;
    const med = lats.length ? lats.slice().sort((a, b) => a - b)[Math.floor(lats.length / 2)] : null;
    const today = dayOf(Date.now());
    return {
      rows,
      summary: {
        totalChars: chars.length,
        seenChars: seen,
        events: kept.length,
        sessions: Object.keys(sess).length,
        latency: med == null ? null : Math.round(med),
        todayTaps: kept.filter(e => e.kind === "tap" && e.day === today).length,
        quizN: kept.filter(e => e.kind === "quiz").length,
        quizOK: kept.filter(e => e.kind === "quiz" && e.ok).length,
      },
    };
  }

  function exportData(labelMap) {
    return {
      version: VERSION,
      exportedAt: new Date().toISOString(),
      events: events(),
      labels: labelMap || labels(),
    };
  }

  const api = { init, log, events, labels, setLabel, reset, stats, exportData, allChars, dayOf, VERSION };
  root.ShiziTrack = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
