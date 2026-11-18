"use strict";
/*
 * DSE Report: the card UI for the daily report JSON (schema 1).
 *
 * Cards, 1-based. These numbers are the contract with answers[].card, setups[].card and the #card=N deep link:
 *   1          Summary: verdict, lede, at a glance, bullish % strip (answers "Are most stocks rising?" and
 *              "Is it oversold?" point here), the eight answers (tap one to jump to its card)
 *   2          Trend: DSEX P&F status, DSEX with EMA20/50/200 and MACD, bullish percent with 30/50/70 zones
 *   3          Money flow: net flow, 14-session bars, in / flat / out, by sector
 *   4          Sectors
 *   5          Signals: new buys, new sells, beating DSEX, volume (top N of M)
 *   6 .. 5+n   one card per setup (setups[i].card = 6 + i); n = setups.length
 *   6+n        Record dates (period-free)
 *   7+n        Headlines: company news and the papers
 * Setups and record dates are the same for every period. With n = 0 the "What may break out?" answer
 * (card 6) lands on Record dates.
 *
 * Security: every string in the JSON is untrusted. The DOM is built with createElement / textContent only;
 * links are rendered only for https:// URLs.
 */
(function (root) {
  const PERIODS = ["day", "week", "month"];
  const PERIOD_NAMES = { day: "Day", week: "Week", month: "Month" };
  const PERIOD_WORD = { day: "today", week: "this week", month: "this month" };
  const STORE_PERIOD = "dser-period";
  const STORE_HINTED = "dser-hinted";
  const HOLD_MS = 450;
  const MOVE_TOL = 10;
  const CLICK_SUPPRESS_MS = 600;
  const SHEET_CLOSE_MS = 220;
  const SHEET_DRAG_CLOSE_PX = 90;
  const HINT_MS = 4500;
  const VIBRATE_MS = 15;
  const BASE_CARDS = 5;
  const SCHEMA = 1;
  const DATA_URL = "/data/latest.json";
  const META_URL = "/data/meta.json";
  const EMPTY_TEXT = "No report saved yet. It downloads after 16:50 on trading days.";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DASH = "–";
  const MAX_ERROR_CHARS = 140;
  const MAX_PF_BOXES = 40;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const NOTES = {
    flow: "Money flow is the turnover of stocks that closed higher minus the turnover of stocks that closed lower, in Tk crore (turnover = volume × close).",
    lastBuy: "DSE settles two sessions after the trade, so the last day to buy is two trading sessions before the record date. Holidays can move it.",
    dividend: "Cash dividends are a percentage of the Tk 10 face value: 105% pays Tk 10.50 a share. Stock dividends are bonus shares, 10% = 1 for every 10 held.",
  };

  // ---------- small helpers ----------
  const isNum = v => typeof v === "number" && isFinite(v);
  const str = v => (typeof v === "string" ? v : isNum(v) ? String(v) : "");
  const arr = v => (Array.isArray(v) ? v : []);
  const obj = v => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const group = s => s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  function num(v, d = 1) {
    if (!isNum(v)) return DASH;
    const s = Math.abs(v).toFixed(d), parts = s.split(".");
    const neg = v < 0 && Number(s) !== 0;
    return (neg ? "−" : "") + group(parts[0]) + (parts[1] ? "." + parts[1] : "");
  }
  function signed(v, d = 1, suffix = "") {
    if (!isNum(v)) return DASH;
    const zero = Number(Math.abs(v).toFixed(d)) === 0;
    return (zero ? "" : v > 0 ? "+" : "−") + num(Math.abs(v), d) + suffix;
  }
  const pct = (v, d = 1) => signed(v, d, "%");
  const toneOf = v => (!isNum(v) ? "muted" : v > 0 ? "up" : v < 0 ? "down" : "muted");
  const toneWord = t => (t === "up" || t === "down" || t === "warn" ? t : "muted");
  const arrow = t => (t === "up" ? "▲" : t === "down" ? "▼" : "■");
  const textTone = s => (/^\+/.test(s) ? "up" : /^[−-]\d/.test(s) ? "down" : "muted");
  const plural = (n, one, many) => (n === 1 ? one : many || one + "s");

  function parseDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str(iso));
    if (!m) return null;
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    return isNaN(d.getTime()) ? null : d;
  }
  function dayLabel(iso) {
    const d = parseDate(iso);
    return d ? `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}` : "";
  }
  function clockTime(iso) {
    if (typeof iso !== "string" || !iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  const colWord = c => (c === "X" ? "rising X column" : c === "O" ? "falling O column" : "");
  const lastNum = list => { const a = arr(list); for (let i = a.length - 1; i >= 0; i--) if (isNum(a[i])) return a[i]; return null; };

  // ---------- DOM builders (no HTML strings anywhere) ----------
  function append(el, kids) {
    for (const k of kids.flat(Infinity)) {
      if (k === null || k === undefined || k === false || k === "") continue;
      el.appendChild(typeof k === "object" ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    const p = props || {};
    for (const k of Object.keys(p)) {
      const v = p[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") el.textContent = String(v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    return append(el, kids);
  }
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(SVG_NS, tag);
    const a = attrs || {};
    for (const k of Object.keys(a)) if (a[k] !== null && a[k] !== undefined) el.setAttribute(k, String(a[k]));
    return append(el, kids);
  }
  const para = (text, cls) => (str(text) ? h("p", { class: cls }, str(text)) : null);
  const h4 = text => h("h4", null, text);
  const lbl = text => h("div", { class: "lbl" }, text);
  const panel = (...kids) => h("div", { class: "card stack" }, kids);
  const chip = (text, tone) => (str(text) ? h("span", { class: "chip " + (tone || "") }, str(text)) : null);
  const ul = items => { const li = items.filter(Boolean); return li.length ? h("ul", null, li.map(x => h("li", null, x))) : null; };
  const none = text => h("p", { class: "small muted" }, text);
  function safeLink(href, text, cls) {
    if (typeof href === "string" && href.startsWith("https://")) {
      return h("a", { href, target: "_blank", rel: "noopener noreferrer", class: cls }, text);
    }
    return h("span", { class: cls }, text);
  }
  function kv(pairs) {
    return h("div", { class: "k2 small" }, pairs.filter(Boolean).map(([k, v, cls]) =>
      h("div", null, h("div", { class: "muted" }, k), h("b", { class: "mono " + (cls || "") }, v))));
  }
  function table(head, rows, cls, caption) {
    return h("table", { class: "tbl " + (cls || "") }, caption ? h("caption", { class: "lbl" }, caption) : null,
      h("thead", null, h("tr", null, head.map(t => h("th", { scope: "col" }, t)))),
      h("tbody", null, rows.map(r => h("tr", null, r.map(c => (Array.isArray(c) ? h("td", { class: c[1] }, c[0]) : h("td", null, c)))))));
  }

  // ---------- charts (inline SVG from the JSON arrays; null values break the line) ----------
  function linePath(vals, x, y) {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (!isNum(v)) { pen = false; return; }
      d += (pen ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1);
      pen = true;
    });
    return d;
  }
  function extent(...lists) {
    const all = lists.flat().filter(isNum);
    if (!all.length) return null;
    let lo = Math.min(...all), hi = Math.max(...all);
    if (lo === hi) { lo -= 1; hi += 1; }
    return [lo, hi];
  }
  const pathEl = (d, cls) => (d ? s("path", { d, class: cls }) : null);

  function trendChart(tr, k) {
    const close = arr(tr.close), lines = [["EMA200", arr(tr.ema200), "ln-muted dash"], ["EMA50", arr(tr.ema50), "ln-warn"],
      ["EMA20", arr(tr.ema20), "ln-acc"], ["DSEX", close, "ln-ink thick"]];
    const ex = extent(...lines.map(l => l[1]));
    if (!ex) return none("No DSEX series in this report.");
    const W = 320, H = 132, MH = 46, R = 46, n = Math.max(2, ...lines.map(l => l[1].length));
    const pad = (ex[1] - ex[0]) * 0.06, lo = ex[0] - pad, hi = ex[1] + pad;
    const x = i => (i / (n - 1)) * (W - R), y = v => 4 + (1 - (v - lo) / (hi - lo)) * (H - 10);
    const shadeK = clamp(isNum(k) ? k : 1, 1, n), x0 = x(n - shadeK) - (shadeK === 1 ? 3 : 0);
    const ends = lines.map(([l, a, c]) => ({ l, c, v: lastNum(a) })).filter(e => isNum(e.v)).map(e => ({ ...e, y: y(e.v) })).sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 11) ends[i].y = ends[i - 1].y + 11;
    const label = "DSEX " + num(lastNum(close)) + ", " + ends.filter(e => e.l !== "DSEX").map(e => e.l + " " + num(e.v)).join(", ") + "; MACD below";
    return s("svg", { viewBox: `0 0 ${W} ${H + MH + 10}`, width: "100%", role: "img", "aria-label": label, class: "chart" },
      s("rect", { x: x0.toFixed(1), y: 0, width: (W - R - x0 + 2).toFixed(1), height: H + MH + 10, class: "shade" }),
      [0.25, 0.75].map(f => { const v = lo + (hi - lo) * f; return [s("line", { x1: 0, x2: W - R, y1: y(v).toFixed(1), y2: y(v).toFixed(1), class: "ln-grid" }), s("text", { x: 2, y: (y(v) - 3).toFixed(1), class: "tx-muted" }, num(Math.round(v / 10) * 10, 0))]; }),
      lines.map(([, a, c]) => pathEl(linePath(a, x, y), c)),
      ends.map(e => s("text", { x: W - R + 4, y: (e.y + 3).toFixed(1), class: "tx-end " + e.c.split(" ")[0].replace("ln-", "tx-") }, e.l)),
      macdBars(obj(tr.macd), x, H + 6, MH, W - R, n));
  }
  function macdBars(m, x, top, MH, w, n) {
    const hist = arr(m.hist), line = arr(m.line), sig = arr(m.signal);
    const ex = extent(hist.map(v => (isNum(v) ? Math.abs(v) : null)), line.map(v => (isNum(v) ? Math.abs(v) : null)), sig.map(v => (isNum(v) ? Math.abs(v) : null)));
    if (!ex) return null;
    const mabs = ex[1] || 1, my = v => top + MH / 2 - (v / mabs) * (MH / 2 - 2), bw = (w / n) * 0.7;
    return [s("line", { x1: 0, x2: w, y1: my(0).toFixed(1), y2: my(0).toFixed(1), class: "ln-border" }),
      hist.map((v, i) => (isNum(v) ? s("rect", { x: (x(i) - bw / 2).toFixed(1), y: Math.min(my(0), my(v)).toFixed(1), width: bw.toFixed(1),
        height: Math.max(0.5, Math.abs(my(v) - my(0))).toFixed(1), class: (v >= 0 ? "f-up" : "f-down") + (i && isNum(hist[i - 1]) && Math.abs(v) < Math.abs(hist[i - 1]) ? " faint" : "") }) : null)),
      pathEl(linePath(line, x, my), "ln-acc"), pathEl(linePath(sig, x, my), "ln-warn"),
      s("text", { x: w + 4, y: (my(0) + 3).toFixed(1), class: "tx-muted" }, "MACD")];
  }

  function bpChart(bp) {
    const path = arr(bp.path);
    if (!path.some(isNum)) return none("No bullish percent history in this report.");
    const W = 320, H = 84, L = 24, n = Math.max(2, path.length);
    const x = i => L + (i / (n - 1)) * (W - L - 4), y = v => 4 + (1 - clamp(v, 0, 100) / 100) * (H - 8);
    const last = lastNum(path);
    return s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", class: "chart",
      "aria-label": `Bullish percent ${num(last)}% over the last ${path.length} sessions; 30 oversold, 70 overbought` },
      s("rect", { x: L, y: y(30).toFixed(1), width: W - L - 4, height: (y(0) - y(30)).toFixed(1), class: "zone-down" }),
      s("rect", { x: L, y: y(100).toFixed(1), width: W - L - 4, height: (y(70) - y(100)).toFixed(1), class: "zone-up" }),
      [30, 50, 70].map(v => [s("line", { x1: L, x2: W - 4, y1: y(v).toFixed(1), y2: y(v).toFixed(1), class: v === 50 ? "ln-border dash" : "ln-grid" }),
        s("text", { x: 2, y: (y(v) + 3).toFixed(1), class: "tx-muted" }, String(v))]),
      isNum(bp.reverse_at) ? s("line", { x1: L, x2: W - 4, y1: y(bp.reverse_at).toFixed(1), y2: y(bp.reverse_at).toFixed(1), class: "ln-down dash thin" }) : null,
      pathEl(linePath(path, x, y), "ln-acc thick"),
      isNum(last) ? s("circle", { cx: x(path.length - 1).toFixed(1), cy: y(last).toFixed(1), r: 3, class: "f-acc" }) : null);
  }

  function flowChart(vals, k) {
    const a = arr(vals);
    if (!a.some(isNum)) return none("No money flow history in this report.");
    const W = 320, H = 64, m = Math.max(...a.filter(isNum).map(Math.abs)) || 1, bw = W / a.length, kk = clamp(isNum(k) ? k : 1, 1, a.length);
    return s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", class: "chart", "aria-label": `Net money flow, last ${a.length} sessions, Tk crore` },
      s("line", { x1: 0, x2: W, y1: H / 2, y2: H / 2, class: "ln-border" }),
      a.map((v, i) => { if (!isNum(v)) return null; const hh = Math.max(0.5, (Math.abs(v) / m) * (H / 2 - 2));
        return s("rect", { x: (i * bw + 2).toFixed(1), y: (v >= 0 ? H / 2 - hh : H / 2).toFixed(1), width: Math.max(1, bw - 4).toFixed(1), height: hh.toFixed(1), rx: 1.5,
          class: (v >= 0 ? "f-up" : "f-down") + (i >= a.length - kk ? "" : " faint") }); }));
  }

  function ladder(st) {
    const pts = [["Cancel", st.cancel, "down"], ["Close", st.close, "ink"], ["Trigger", st.trigger, "acc"]];
    if (isNum(st.target)) pts.push(["Target", st.target, "up"]);
    else { pts.push(["If triggered", st.objective_if, "up"]); pts.push(["Resistance", st.resistance, "warn"]); }
    const p = pts.filter(q => isNum(q[1])).sort((a, b) => a[1] - b[1]);
    if (p.length < 2) return null;
    const W = 320, lo = p[0][1], hi = p[p.length - 1][1] === lo ? lo + 1 : p[p.length - 1][1], x = v => 14 + ((v - lo) / (hi - lo)) * (W - 28);
    const seg = (a, b, c) => (isNum(a) && isNum(b) ? s("line", { x1: x(Math.min(a, b)).toFixed(1), x2: x(Math.max(a, b)).toFixed(1), y1: 24, y2: 24, class: "seg " + c }) : null);
    // Labels never overlap: each goes on the first row (above, below, then a lower row) with room for it.
    const CH = 5.4, GAP = 6, ROWS = [12, 46, 60], ends = ROWS.map(() => -Infinity);
    const placed = p.map(([l, v, c]) => {
      const text = l + " " + num(v), w = text.length * CH;
      const left = Math.max(2, Math.min(W - 2 - w, x(v) - w / 2));
      let row = ROWS.findIndex((_, k) => left >= ends[k] + GAP);
      if (row < 0) row = ROWS.length - 1;
      ends[row] = left + w;
      return { text, c, v, left, row };
    });
    const H = placed.some(q => q.row === 2) ? 66 : 52;
    return s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", class: "chart ladder",
      "aria-label": str(st.code) + ": " + p.map(q => q[0] + " " + num(q[1])).join(", ") },
      seg(st.cancel, st.close, "ln-down"), seg(st.close, st.trigger, "ln-acc"), seg(st.trigger, hi, "ln-up"),
      placed.map(q => [s("circle", { cx: x(q.v).toFixed(1), cy: 24, r: 5, class: "f-" + q.c }),
        s("text", { x: q.left.toFixed(1), y: ROWS[q.row], "text-anchor": "start", class: "tx-lad tx-" + q.c }, q.text)]));
  }

  function pfSketch(cols, trigger) {
    const c = arr(cols).filter(q => Array.isArray(q) && (q[0] === "X" || q[0] === "O") && isNum(q[1]) && isNum(q[2]) && isNum(q[3]) && q[3] >= 1);
    if (!c.length) return null;
    const ex = extent(c.map(q => q[1]), c.map(q => q[2]), [trigger]);
    const W = 320, H = 96, cw = Math.min(22, (W - 50) / c.length), pad = (ex[1] - ex[0]) * 0.08 || 1;
    const lo = ex[0] - pad, hi = ex[1] + pad, y = v => 4 + (1 - (v - lo) / (hi - lo)) * (H - 8);
    const marks = c.map((q, i) => {
      const boxes = Math.min(MAX_PF_BOXES, Math.round(q[3])), step = boxes > 1 ? (q[2] - q[1]) / (boxes - 1) : 0, cx = 8 + i * cw + cw / 2, r = Math.min(cw * 0.32, ((H - 8) / ((hi - lo) / (step || 1))) * 0.4, 6);
      return Array.from({ length: boxes }, (_, b) => { const cy = y(q[1] + b * step);
        return q[0] === "X" ? s("path", { d: `M${(cx - r).toFixed(1)},${(cy - r).toFixed(1)}L${(cx + r).toFixed(1)},${(cy + r).toFixed(1)}M${(cx + r).toFixed(1)},${(cy - r).toFixed(1)}L${(cx - r).toFixed(1)},${(cy + r).toFixed(1)}`, class: "ln-up" })
          : s("circle", { cx: cx.toFixed(1), cy: cy.toFixed(1), r: r.toFixed(1), class: "ln-down nofill" }); });
    });
    return s("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", class: "chart",
      "aria-label": `Point and figure, last ${c.length} columns` + (isNum(trigger) ? `; buy trigger ${num(trigger)}` : "") },
      isNum(trigger) ? [s("line", { x1: 0, x2: W - 44, y1: y(trigger).toFixed(1), y2: y(trigger).toFixed(1), class: "ln-acc dash" }),
        s("text", { x: W - 40, y: (y(trigger) + 3).toFixed(1), class: "tx-acc tx-end" }, "Trigger")] : null, marks);
  }

  function bpStrip(bp) {
    if (!isNum(bp.value)) return null;
    const mark = h("i", { class: "bp-mark" });
    mark.style.left = `calc(${clamp(bp.value, 0, 100)}% - 2px)`;
    return h("div", { class: "card stack" },
      lbl(`Bullish percent ${num(bp.value)}%` + (colWord(bp.column) ? " · " + colWord(bp.column) : "")),
      h("div", { class: "bp-strip", role: "img", "aria-label": `Bullish percent ${num(bp.value)}% on a scale with 30 oversold and 70 overbought` }, mark),
      h("div", { class: "row small muted" }, h("span", null, "oversold 30"), h("span", null, "50"), h("span", null, "70 overbought")));
  }

  // ---------- shared rows ----------
  function stockRow(it, kind) {
    const q = obj(it);
    return h("div", null,
      h("div", { class: "row" }, h("span", null, h("span", { class: "code" }, str(q.code)), " ", h("span", { class: "small muted" }, str(q.sector))),
        h("span", { class: "mono small " + toneOf(q.chg_pct) }, num(q.close) + " " + pct(q.chg_pct))),
      h("div", { class: "chips" }, chip(str(q.pattern), kind === "sell" ? "down" : kind === "buy" ? "up" : ""),
        isNum(q.target) ? chip("target " + num(q.target)) : null, isNum(q.stop) ? chip("stop " + num(q.stop)) : null,
        isNum(q.rvol) ? chip("RVOL " + num(q.rvol) + "×") : null, arr(q.chips).map(c => chip(str(obj(c).text), toneWord(obj(c).tone)))));
  }
  function glanceTable(glance, label) {
    const rows = arr(glance).filter(Array.isArray).map(g => [str(g[0]), [str(g[1]) || DASH, "mono"], [str(g[2]), "mono " + textTone(str(g[2]))]]);
    if (!rows.length) return null;
    return table(["", "Value", "Change"], rows, "glance", "At a glance" + (str(label) ? " · " + str(label) : ""));
  }
  function whyBlock(items) {
    const list = arr(items).filter(x => x !== null && x !== undefined && x !== "");
    return list.length ? h("section", { class: "why" }, h4("Why?"), ul(list)) : null;
  }
  // The report's own answers that point at this card: "Is DSEX in an uptrend? ▲ Buy: <detail>"
  function answersFor(ctx, card) {
    return arr(obj(ctx.P.summary).answers).map(obj).filter(a => a.card === card)
      .map(a => [h("b", { class: toneWord(a.tone) }, `${str(a.q)} ${arrow(a.tone)} ${str(a.state) || DASH}. `), str(a.detail)]);
  }

  // ---------- the Why? write-up (docs/WHY-CONTRACT.md "Shared shape"), one renderer for setups and market cards ----------
  const VIEW_TONE = { up: "up", down: "down", flat: "flat" };
  const MARKS = { up: ["✓", "up", "for"], down: ["✗", "down", "against"], flat: ["–", "muted", "neutral"] };
  const TILE_TONE = { acc: "acc", up: "up", down: "down" };
  const hasView = v => !!(str(obj(v).verdict) || str(obj(v).thesis) || arr(obj(v).pillars).some(p => str(obj(p).name)));
  function verdictBox(v) {
    if (!str(v.verdict) && !str(v.badge)) return null;
    return h("div", { class: "verdict " + (VIEW_TONE[v.tone] || "flat") }, str(v.badge) ? h("b", { class: "badge", "aria-hidden": "true" }, str(v.badge)) : null,
      h("div", null, str(v.verdict) ? h("b", { class: "vtext" }, str(v.verdict)) : null, para(v.sub, "small muted")));
  }
  function pillarTable(list) {
    const rows = arr(list).map(obj).filter(p => str(p.name)).map(p => {
      const m = MARKS[p.mark] || MARKS.flat;
      return h("tr", null, h("td", { class: "mark " + m[1], "aria-label": m[2] }, m[0]), h("td", { class: "pillar" }, str(p.name)),
        h("td", { class: m[1] === "up" ? "" : m[1] }, str(p.reading) || DASH));
    });
    return rows.length ? [h4("Why?"), h("table", { class: "tbl pillars" },
      h("thead", null, h("tr", null, h("th", { scope: "col", "aria-label": "For or against" }), h("th", { scope: "col" }, "Pillar"), h("th", { scope: "col" }, "Reading"))),
      h("tbody", null, rows))] : null;
  }
  // Levels can be whole numbers (5,472, a count of buys): those show without a decimal; prices keep one.
  function planTiles(list, title) {
    const tiles = arr(list).map(obj).filter(t => str(t.label) && isNum(t.value)).map(t => {
      const d = title === "Levels" && Number.isInteger(t.value) ? 0 : 1;
      return h("div", { class: "tile" }, h("span", null, str(t.label)), h("b", { class: "mono " + (TILE_TONE[t.tone] || "") }, t.value === t.pct ? pct(t.pct) : num(t.value, d)),
        isNum(t.pct) && t.value !== t.pct ? h("span", { class: "mono" }, pct(t.pct)) : null);   // a % tile shows its % once
    });
    return tiles.length ? [h4(title), h("div", { class: "plan" }, tiles)] : null;
  }
  function viewBlock(view, title) {
    const v = obj(view);
    if (!hasView(v)) return null;
    return h("section", { class: "view stack" }, verdictBox(v),
      str(v.thesis) ? [h4("Thesis"), para(v.thesis)] : null,
      pillarTable(v.pillars), planTiles(v.plan, title || "Plan"), para(v.plan_note, "small muted"),
      str(v.change_view) ? [h4("What would change our view"), h("p", { class: "change" }, str(v.change_view))] : null,
      para(v.method, "small muted"));
  }

  // ---------- cards ----------
  function summaryCard(ctx) {
    const P = ctx.P, sm = obj(P.summary), bp = obj(obj(P.market).bp), answers = arr(sm.answers).map(obj);
    const grid = () => h("div", { class: "ans" }, answers.map(a => h("button", { type: "button", "data-go": isNum(a.card) ? a.card : 1 },
      h("span", null, str(a.q)), h("b", { class: toneWord(a.tone) }, arrow(a.tone) + " " + (str(a.state) || DASH)))));
    const notif = obj(ctx.r.notification);
    return { kick: "Summary · " + (str(P.label) || PERIOD_NAMES[ctx.p]), title: str(sm.verdict) || "The market " + PERIOD_WORD[ctx.p],
      front: () => [para(sm.lede), glanceTable(sm.glance, P.label), bpStrip(bp), grid()],
      back: () => [para(sm.lede), h4("The eight answers"),
        ul(answers.map(a => [h("b", { class: toneWord(a.tone) }, `${str(a.q)} ${arrow(a.tone)} ${str(a.state) || DASH}. `), str(a.detail)])),
        glanceTable(sm.glance, P.label),
        ctx.p === "day" && arr(notif.lines).length ? [h4("Today's alert"), para(notif.title), ul(arr(notif.lines).map(str))] : null],
      view: () => obj(obj(ctx.P.views).summary), viewTitle: "Levels",
      why: () => answersFor(ctx, 1) };
  }

  function pfStatus(pf) {
    const t = pf.status === "BUY" ? "up" : pf.status === "SELL" ? "down" : "muted";
    return panel(h("div", { class: "chips" }, chip(`${arrow(t)} P&F ${str(pf.status) || DASH}`, t), chip(colWord(pf.column), pf.column === "X" ? "up" : "down"), chip(str(pf.pattern))),
      kv([["Next box", num(pf.next_box)], ["Reverses at", num(pf.reverse_at)], ["Objective", num(pf.target), "up"], ["Stop", num(pf.stop), "down"]]));
  }
  function macdText(tr) {
    const ms = obj(tr.macd_state), m = obj(tr.macd), x = obj(ms.last_signal_cross), run = ms.hist_run;
    const parts = [`MACD ${num(lastNum(m.line))}, signal ${num(lastNum(m.signal))}, histogram ${num(lastNum(m.hist))}.`];
    if (typeof ms.above_signal === "boolean" && typeof ms.above_zero === "boolean") parts.push(`MACD is ${ms.above_signal ? "above" : "below"} its signal line and ${ms.above_zero ? "above" : "below"} zero.`);
    if (isNum(run) && run !== 0) parts.push(`The histogram has ${run > 0 ? "risen" : "fallen"} ${Math.abs(run)} ${plural(Math.abs(run), "session")} in a row.`);
    if (str(x.kind) && dayLabel(x.date)) parts.push(`Last signal-line cross: ${str(x.kind)}, on ${dayLabel(x.date)}.`);
    return parts.join(" ");
  }
  function trendCard(ctx) {
    const P = ctx.P, tr = obj(P.trend), mk = obj(P.market), pf = obj(mk.pf), bp = obj(mk.bp), last = obj(tr.last), reg = obj(mk.regime), cross = obj(tr.cross);
    const maRows = ["ema20", "ema50", "ema200"].map(k => [k.toUpperCase(), [num(last[k]), "mono"], [pct(obj(last.dist_pct)[k]), toneOf(obj(last.dist_pct)[k])],
      [obj(last.slope)[k] === "rising" ? "▲ rising" : obj(last.slope)[k] === "falling" ? "▼ falling" : DASH, obj(last.slope)[k] === "rising" ? "up" : "down"]]);
    const bpLine = `Bullish percent ${num(bp.value)}%` + (str(bp.zone) ? `, ${str(bp.zone)}` : "") + (colWord(bp.column) ? `, in a ${colWord(bp.column)}` : "") +
      (dayLabel(bp.column_since) ? ` since ${dayLabel(bp.column_since)}` : "") + (isNum(bp.reverse_at) ? `; ${num(bp.reverse_at)}% would reverse it.` : ".");
    return { kick: "Trend · DSEX", title: str(tr.headline) || "DSEX trend",
      front: () => [pfStatus(pf), panel(trendChart(tr, tr.period_sessions)), para(tr.sentence),
        panel(lbl(`Bullish percent ${num(bp.value)}%` + (str(bp.zone) ? " · " + str(bp.zone) : "")), bpChart(bp)),
        str(reg.name) ? h("div", { class: "chips" }, chip("Regime: " + str(reg.name), "acc")) : null],
      back: () => [h4("Point and figure"), ul(arr(mk.levels).map(obj).map(l => [h("b", null, str(l.label) + ". "), str(l.text)])),
        str(pf.trend) && isNum(pf.trend_level) ? para(`The ${pf.trend === "bull" ? "bullish support" : "bearish resistance"} line is at ${num(pf.trend_level, 0)}.`) : null,
        h4("Averages"), table(["Average", "Value", "Close vs", "Slope (5 days)"], maRows),
        para(tr.sentence), str(cross.kind) ? para(`Latest crossover: ${str(cross.kind)} on ${dayLabel(cross.date) || DASH}.`) : null,
        h4("MACD (12, 26, 9)"), para(macdText(tr)), h4("Bullish percent"), para(bpLine),
        str(reg.name) ? [h4("Regime"), para(str(reg.name) + (str(reg.note) ? ": " + str(reg.note) + "." : "."))] : null],
      view: () => obj(obj(ctx.P.views).trend), viewTitle: "Levels",
      why: () => answersFor(ctx, 2) };
  }

  function flowCard(ctx) {
    const P = ctx.P, f = obj(P.flow), net = f.net_cr;
    const total = [f.in_cr, f.flat_cr, f.out_cr].filter(isNum).reduce((a, b) => a + b, 0);
    const vsAvg = isNum(f.vs_avg20) ? `${pct((f.vs_avg20 - 1) * 100, 0)} vs its 20-session average` : "";
    const bar = () => { if (!total) return null; const b = h("div", { class: "bar", role: "img", "aria-label": `In ${num(f.in_cr)}, flat ${num(f.flat_cr)}, out ${num(f.out_cr)} Tk crore` });
      [["in_cr", "f-up-bg"], ["flat_cr", "f-flat-bg"], ["out_cr", "f-down-bg"]].forEach(([k, c]) => { if (!isNum(f[k])) return; const i = h("i", { class: c }); i.style.width = (f[k] / total) * 100 + "%"; b.appendChild(i); }); return b; };
    const bySector = Object.keys(obj(f.by_sector)).map(k => [k, f.by_sector[k]]).filter(e => isNum(e[1])).sort((a, b) => b[1] - a[1]);
    const title = isNum(net) ? `Tk ${num(Math.abs(net), 0)} crore net into ${net >= 0 ? "rising" : "falling"} stocks` : "Money flow";
    return { kick: "Money flow · " + (str(P.label) || PERIOD_NAMES[ctx.p]), title,
      front: () => [panel(flowChart(f.last14, f.sessions), bar(), h("div", { class: "row small" }, h("span", { class: "up" }, "▲ In " + num(f.in_cr, 0)), h("span", { class: "muted" }, "Flat " + num(f.flat_cr, 0)), h("span", { class: "down" }, "▼ Out " + num(f.out_cr, 0)))),
        para(`Inflows on ${isNum(f.inflow_sessions_14) ? f.inflow_sessions_14 : DASH} of the last ${arr(f.last14).length || 14} sessions. Turnover Tk ${num(f.turnover_cr, 0)} crore` + (vsAvg ? `, ${vsAvg}.` : ".")),
        para(`${num(f.adv, 0)} up · ${num(f.dec, 0)} down · ${num(f.unch, 0)} unchanged`, "small")],
      back: () => [para(NOTES.flow),
        table(["", "Tk crore"], [["Turnover", [num(f.turnover_cr), "mono"]], ["Average a session", [num(f.turnover_avg_cr), "mono"]],
          ["Into rising stocks", [num(f.in_cr), "mono up"]], ["Into falling stocks", [num(f.out_cr), "mono down"]], ["Unchanged stocks", [num(f.flat_cr), "mono"]], ["Net", [signed(net), "mono " + toneOf(net)]]]),
        vsAvg ? para(`Turnover a session is ${vsAvg}.`) : null,
        h4("By sector " + PERIOD_WORD[ctx.p]), bySector.length ? table(["Sector", "Net Tk cr"], bySector.map(([k, v]) => [k, [signed(v), "mono " + toneOf(v)]])) : none("No sector flows."),
        h4("Last 14 sessions, oldest first"), para(arr(f.last14).map(v => signed(v, 0)).join(" · "), "mono small")],
      view: () => obj(obj(ctx.P.views).flow), viewTitle: "Levels",
      why: () => answersFor(ctx, 3) };
  }

  function sectorsCard(ctx) {
    const P = ctx.P, sec = obj(P.sectors), rows = arr(sec.rows).map(obj), hl = arr(sec.highlights).map(obj);
    const colTxt = c => (c === "X" ? "▲ X" : c === "O" ? "▼ O" : DASH), colTone = c => (c === "X" ? "up" : c === "O" ? "down" : "muted");
    const line = r => h("div", { class: "row" }, h("b", null, str(r.sector)), h("span", { class: "mono small" }, h("span", { class: toneOf(r.chg_pct) }, pct(r.chg_pct)), " · BP " + num(r.bp, 0) + "% ", h("span", { class: colTone(r.bp_column) }, colTxt(r.bp_column))));
    const pick = rows.length > 4 ? rows.slice(0, 3).concat(rows.slice(-1)) : rows;
    const title = hl.length >= 2 ? `${str(hl[0].sector)} leads; ${str(hl[hl.length - 1].sector)} is weakest` : rows.length ? `${str(rows[0].sector)} leads` : "Sectors";
    return { kick: "Sectors · " + (str(P.label) || PERIOD_NAMES[ctx.p]), title,
      front: () => [rows.length ? h("div", { class: "card list" }, pick.map(line)) : none("No sector table in this report."), hl.length ? para(arr(hl[0].reasons).slice(0, 2).map(str).join(" ")) : null],
      back: () => [rows.length ? table(["Sector", "Chg", "BP", "Flow cr"], rows.map(r => [str(r.sector), [pct(r.chg_pct), toneOf(r.chg_pct)], [num(r.bp, 0) + "% " + colTxt(r.bp_column), colTone(r.bp_column)], [signed(r.net_cr, 1), toneOf(r.net_cr)]]), "sect") : null,
        hl.map(x => [h4(`${str(x.sector)} ${pct(x.chg_pct)}`), ul(arr(x.reasons).map(str))])],
      view: () => obj(obj(ctx.P.views).sectors), viewTitle: "Levels",
      why: () => answersFor(ctx, 4).concat(arr(obj(P.sectors).highlights).map(obj).slice(0, 1).flatMap(x => arr(x.reasons).map(str))) };
  }

  function signalsCard(ctx) {
    const P = ctx.P, sg = obj(P.signals), c = obj(sg.counts), lists = [["buys", "New P&F buy signals", "buy"], ["sells", "New P&F sell signals", "sell"], ["beating", "Beating DSEX", ""], ["volume", "Volume surge (RVOL 2× or more)", ""]];
    const front = arr(sg.buys).slice(0, 2).map(i => stockRow(i, "buy")).concat(arr(sg.sells).slice(0, 2).map(i => stockRow(i, "sell")));
    return { kick: "Signals · " + (str(P.label) || PERIOD_NAMES[ctx.p]), title: `${num(c.buys, 0)} new ${plural(c.buys, "buy")}, ${num(c.sells, 0)} new ${plural(c.sells, "sell")}`,
      front: () => [front.length ? h("div", { class: "card list" }, front) : none("No new P&F signals in this period."),
        para(`Top ${Math.min(2, arr(sg.buys).length)} of ${num(c.buys, 0)} buys and ${Math.min(2, arr(sg.sells).length)} of ${num(c.sells, 0)} sells by RVOL. Hold for all of them.`, "small")],
      back: () => lists.map(([k, t, kind]) => [h4(`${t} · top ${arr(sg[k]).length} of ${num(c[k], 0)}`), arr(sg[k]).length ? h("div", { class: "list" }, arr(sg[k]).map(i => stockRow(i, kind))) : none("None in this period.")])
        .concat([para("Chips: pattern, P&F target and stop, relative volume, MACD state, moving averages and money flow index (14). A squeeze chip marks unusually narrow Bollinger Bands.", "small muted")]),
      view: () => obj(obj(ctx.P.views).signals), viewTitle: "Levels",
      why: () => answersFor(ctx, 5) };
  }

  function setupCard(st, i, n) {
    const conds = arr(st.conditions).map(obj), reasons = arr(st.reasoning).map(str).filter(Boolean);
    const hasTarget = isNum(st.target);
    const check = () => h("div", { class: "check" }, conds.map(c => h("span", { class: c.met === true ? "ok" : "" }, str(c.label))));
    const scoreChip = () => chip(`${num(st.score, 0)} of ${conds.length || 7} conditions`, isNum(st.score) && st.score >= 5 ? "up" : "warn");
    const values = () => kv([["Close", num(st.close)], ["Trigger", num(st.trigger) + " " + pct(st.trigger_pct), "acc"],
      hasTarget ? ["Target", num(st.target) + " " + pct(st.target_pct), "up"] : ["Objective if triggered", num(st.objective_if) + " " + pct(st.objective_if_pct), "up"],
      ["Cancel below", num(st.cancel) + " " + pct(st.cancel_pct), "down"], !hasTarget && isNum(st.resistance) ? ["Resistance", num(st.resistance) + " " + pct(st.resistance_pct), "warn"] : null]);
    const caution = () => (str(st.caution) ? h("p", { class: "warnline" }, h("b", { class: "warn" }, "⚠ "), str(st.caution)) : null);
    const v = obj(st.view), viewed = hasView(v), GRADE_TONE = { A: "up", B: "acc", C: "warn", D: "down" };
    const gradeChip = () => (str(v.grade) ? chip(`Grade ${str(v.grade)} · ${str(v.confidence) || DASH} confidence`, GRADE_TONE[v.grade] || "") : null);
    const condList = () => (conds.length ? [h4(`The ${conds.length} ${plural(conds.length, "condition")}`),
      ul(conds.map(c => [h("b", { class: c.met === true ? "up" : "muted" }, c.met === true ? `✓ ${str(c.label)}. ` : `✗ ${str(c.label)} (not met). `), str(c.help)]))] : null);
    return { kick: `Watch · ${i + 1} of ${n}`, title: `${str(st.code) || "Setup"}: one box from a P&F buy at ${num(st.trigger)}`, periodFree: true,
      front: () => [h("div", { class: `card stack${str(st.caution) ? " cautious" : ""}` }, h("div", { class: "row" }, h("span", { class: "small muted" }, str(st.sector)), scoreChip()), gradeChip(), ladder(st), values(), check()),
        caution(), para(reasons[0])],
      // With a view, its Plan tiles replace the values and reasoning; the chart detail stays below it.
      back: () => [ladder(st), viewed ? null : [values(), reasons.map(r => para(r))], caution(),
        h4("Point and figure, last columns"), pfSketch(st.pf_cols, st.trigger) || none("No P&F columns in this report."), condList()],
      view: () => v, viewTitle: "Plan",
      why: () => [] };
  }

  function recordRow(rec) {
    const d = parseDate(rec.record_date), late = rec.can_still_buy === false;
    const sub = [late ? `Too late to buy (last day was ${str(rec.last_buy_label) || DASH})` : `Last day to buy ${str(rec.last_buy_label) || DASH}`,
      isNum(rec.cash_yield_pct) ? `yield ${num(rec.cash_yield_pct)}%` : null, isNum(rec.since_declared_pct) ? `${pct(rec.since_declared_pct)} since declared` : null].filter(Boolean).join(" · ");
    return h("div", { class: "rec" }, h("div", { class: "date" }, h("b", null, d ? String(d.getUTCDate()) : DASH), h("span", null, d ? MONTHS[d.getUTCMonth()] : "")),
      h("div", null, h("div", null, h("span", { class: "code" }, str(rec.code)), " · ", h("b", null, str(rec.dividend_text) || "No dividend")), h("div", { class: "small muted" }, sub)),
      chip(late ? "Too late to buy" : `Buy by ${str(rec.last_buy_label) || DASH}`, late ? "warn" : "acc"));
  }
  function recordsCard(r) {
    const recs = arr(r.records).map(obj), firstBuy = recs.find(x => x.can_still_buy === true);
    const title = firstBuy ? `${str(firstBuy.code)}: buy by ${str(firstBuy.last_buy_label) || DASH} for the record date` : recs.length ? `${recs.length} record ${plural(recs.length, "date")} ahead` : "No record dates ahead";
    return { kick: "Record dates", title, periodFree: true,
      front: () => [recs.length ? h("div", { class: "card list" }, recs.slice(0, 4).map(recordRow)) : none("No future record dates in this report."), recs.length > 4 ? para(`Hold for all ${recs.length}.`, "small") : null],
      back: () => [recs.length ? h("div", { class: "list" }, recs.map(recordRow)) : none("No future record dates in this report."),
        h4("How the dates work"), para(NOTES.lastBuy), para(NOTES.dividend)],
      why: () => [] };
  }

  function newsRow(n) {
    return h("div", null, h("div", { class: "src" }, "DSE" + (str(n.code) ? " · " : ""), str(n.code) ? h("span", { class: "code" }, str(n.code)) : null, str(n.kind) ? " · " + str(n.kind) : "", dayLabel(n.date) ? " · " + dayLabel(n.date) : ""),
      h("div", { class: "ttl" }, str(n.text)), isNum(n.move_pct) ? h("div", { class: "small " + toneOf(n.move_pct) }, `${arrow(toneOf(n.move_pct))} ${pct(n.move_pct)} on the day`) : null);
  }
  function paperRow(p) {
    return h("div", null, h("div", { class: "src" }, str(p.source) || "Paper", str(p.section) ? " · " + str(p.section) : "", dayLabel(p.published) ? " · " + dayLabel(p.published) : ""),
      safeLink(p.link, str(p.title), "ttl"), arr(p.tags).length ? h("div", { class: "chips" }, arr(p.tags).map(t => chip(str(t)))) : null);
  }
  function headlinesCard(ctx) {
    const P = ctx.P, news = arr(P.news).map(obj), papers = arr(P.papers).map(obj).filter(p => str(p.title)), failed = arr(ctx.r.papersFailed).map(str).filter(Boolean);
    const title = papers.length ? str(papers[0].title) : news.length ? `${str(news[0].code)}: ${str(news[0].text)}` : "No headlines";
    const failNote = () => (failed.length ? para("Could not reach: " + failed.join(", ") + ".", "small muted") : null);
    return { kick: "Headlines · " + (str(P.label) || PERIOD_NAMES[ctx.p]), title,
      front: () => [news.length || papers.length ? h("div", { class: "card list" }, news.slice(0, 2).map(newsRow), papers.slice(0, 3).map(paperRow)) : none("No company news or headlines in this period."), failNote()],
      back: () => [h4("Company announcements (DSE)"), news.length ? h("div", { class: "list" }, news.map(newsRow)) : none("None in this period."),
        h4("In the papers"), papers.length ? h("div", { class: "list" }, papers.map(paperRow)) : none("No headlines in this period."), failNote(),
        para("Headlines link to the newspaper's own page; the app shows headlines only.", "small muted")],
      why: () => [] };
  }

  function cardDefs(report, period) {
    const ctx = { r: report, p: period, P: obj(obj(report.periods)[period]) };
    const setups = arr(report.setups).map(obj);
    return [summaryCard(ctx), trendCard(ctx), flowCard(ctx), sectorsCard(ctx), signalsCard(ctx)]
      .concat(setups.map((st, i) => setupCard(st, i, setups.length)), [recordsCard(report), headlinesCard(ctx)]);
  }

  // ---------- hold gesture (separable so it can be unit-tested) ----------
  function createHold(opts) {
    const o = opts || {};
    const ms = isNum(o.holdMs) ? o.holdMs : HOLD_MS, tol = isNum(o.moveTol) ? o.moveTol : MOVE_TOL;
    const now = o.now || (() => Date.now()), setT = o.setTimeout || setTimeout, clrT = o.clearTimeout || clearTimeout;
    let press = null, heldAt = -Infinity;
    const api = {
      down(x, y, target) {
        api.cancel();
        press = { x, y, target, t: setT(() => { const tg = press && press.target; press = null; heldAt = now(); if (o.onPress) o.onPress(tg, false); if (o.onHold) o.onHold(tg); }, ms) };
        if (o.onPress) o.onPress(target, true);
      },
      move(x, y) { if (press && Math.hypot(x - press.x, y - press.y) > tol) api.cancel(); },
      up() { api.cancel(); },
      cancel() { if (!press) return; clrT(press.t); const tg = press.target; press = null; if (o.onPress) o.onPress(tg, false); },
      heldRecently() { return now() - heldAt < CLICK_SUPPRESS_MS; },
      suppressClick() { if (!api.heldRecently()) return false; heldAt = -Infinity; return true; },
      get pressing() { return press !== null; },
    };
    return api;
  }

  // ---------- app state and shell ----------
  const state = { report: null, meta: null, period: "day", index: 0, cards: [], els: {}, hold: null, sheetIndex: -1, lastFocus: null };

  function storeGet(k) { try { return root.localStorage ? root.localStorage.getItem(k) : null; } catch (e) { return null; } }
  function storeSet(k, v) { try { if (root.localStorage) root.localStorage.setItem(k, v); } catch (e) { /* storage off: keep the default */ } }

  function buildShell() {
    const E = state.els;
    E.prog = h("div", { class: "prog", "aria-hidden": "true" });
    E.date = h("div", { class: "dt" }, "DSE Report");
    E.saved = h("div", { class: "saved" });
    E.seg = h("div", { class: "seg", role: "group", "aria-label": "Report period" },
      PERIODS.map(p => h("button", { type: "button", "data-period": p, "aria-pressed": "false" }, PERIOD_NAMES[p])));
    E.offbar = h("div", { class: "offbar", role: "status" }); E.offbar.hidden = true;
    E.track = h("main", { class: "track", tabindex: "0", "aria-roledescription": "carousel", "aria-label": "Report cards" });
    E.hint = h("div", { class: "hint" }, "Swipe for the next card · hold a card for the full story"); E.hint.hidden = true;
    E.scrim = h("div", { class: "scrim" }); E.scrim.hidden = true;
    E.sheetKick = h("div", { class: "kick" }); E.sheetTitle = h("h3", { id: "sheetTitle" });
    E.sheetClose = h("button", { type: "button", class: "x", "aria-label": "Close" }, "✕");
    E.sheetBody = h("div", { class: "body" });
    E.grab = h("div", { class: "grab", "aria-hidden": "true" }, h("i"));
    E.sheet = h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "sheetTitle" }, E.grab,
      h("div", { class: "head" }, h("div", null, E.sheetKick, E.sheetTitle), E.sheetClose), E.sheetBody);
    E.sheet.hidden = true;
    const app = h("div", { class: "app" }, E.prog, h("header", { class: "top" }, h("div", null, E.date, E.saved), E.seg), E.offbar, E.track, E.hint, E.scrim, E.sheet);
    const host = document.getElementById("app") || document.body;
    host.replaceChildren(app);
    wireEvents();
  }

  function showMeta() {
    const E = state.els, m = state.meta, t = clockTime(m.savedAt);
    E.saved.textContent = t ? `Saved ${t}` + (m.offline ? " · offline" : "") : m.offline ? "Offline" : "";
    let msg = "";
    if (m.offline) msg = t ? `Offline · showing the report saved at ${t}. It updates when you're back online.` : "Offline · showing the last saved report.";
    else if (m.error) msg = "The last download failed: " + m.error.slice(0, MAX_ERROR_CHARS) + (t ? `. Showing the report saved at ${t}.` : "");
    E.offbar.textContent = msg;
    E.offbar.hidden = !msg;
  }

  function showMessage(text) {
    const E = state.els;
    state.cards = [];
    E.prog.replaceChildren();
    E.track.replaceChildren(h("section", { class: "pg" }, h("article", { class: "cardx empty" }, h("div", { class: "kick" }, "DSE Report"), h("h2", null, "Nothing to show yet"), h("p", null, text))));
  }

  function currentPeriod() { return PERIODS.includes(state.period) ? state.period : "day"; }

  function render() {
    const E = state.els, r = state.report, defs = cardDefs(r, currentPeriod());
    state.cards = defs;
    state.index = clamp(state.index, 0, defs.length - 1);
    E.date.textContent = "DSE Report" + (dayLabel(r.asOf) ? " · " + dayLabel(r.asOf) : "");
    Array.prototype.forEach.call(E.seg.children, b => b.setAttribute("aria-pressed", String(b.getAttribute("data-period") === state.period)));
    E.track.replaceChildren(...defs.map((c, i) => h("section", { class: "pg", "aria-roledescription": "card", "aria-label": `${i + 1} of ${defs.length}: ${c.kick}`, "data-i": i },
      h("article", { class: "cardx", "data-i": i }, h("span", { class: "ring" }), h("div", { class: "kick" }, c.kick), h("h2", null, c.title), c.front(),
        h("div", { class: "foot" }, h("span", null, `${i + 1} of ${defs.length}` + (c.periodFree ? " · same for every period" : "")), h("span", { class: "hold" }, "Hold for the full story"))))));
    E.prog.replaceChildren(...defs.map(() => h("i")));
    setIndex(state.index);
    E.track.scrollLeft = state.index * (E.track.clientWidth || 0);
  }

  function setIndex(i) {
    const E = state.els, n = state.cards.length;
    if (!n) return;
    state.index = clamp(i, 0, n - 1);
    Array.prototype.forEach.call(E.prog.children, (el, k) => el.setAttribute("class", k <= state.index ? "on" : ""));
    Array.prototype.forEach.call(E.track.children, (el, k) => { if (k === state.index) el.setAttribute("aria-current", "true"); else el.removeAttribute("aria-current"); });
  }

  function reducedMotion() { try { return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) { return false; } }
  function go(i) {
    const track = state.els.track;
    setIndex(i);
    const left = state.index * (track.clientWidth || 0);
    if (typeof track.scrollTo === "function") track.scrollTo({ left, behavior: reducedMotion() ? "auto" : "smooth" });
    else track.scrollLeft = left;
  }

  function setPeriod(p) {
    if (!PERIODS.includes(p)) return;
    state.period = p;
    storeSet(STORE_PERIOD, p);
    if (state.report) render();
    if (state.sheetIndex >= 0 && state.report) fillSheet(state.sheetIndex);
  }

  function cardFromHash() {
    const m = /(?:^#|[#&?])card=(\d+)/.exec(str(root.location && root.location.hash));
    return m ? Number(m[1]) - 1 : null;
  }

  // ---------- bottom sheet ----------
  function fillSheet(i) {
    const E = state.els, c = state.cards[i];
    if (!c) return false;
    E.sheetKick.textContent = c.kick;
    E.sheetTitle.textContent = c.title;
    // A card with a view leads with the write-up and keeps its own detail below a divider; without one, the
    // card's sheet as before, with the answers' Why? list.
    const vb = c.view ? viewBlock(c.view(), c.viewTitle) : null;
    E.sheetBody.replaceChildren(vb ? h("div", { class: "stack" }, vb, h("hr", { class: "divider" }), c.back())
      : h("div", { class: "stack" }, c.back(), whyBlock(c.why ? c.why() : [])));
    E.sheetBody.scrollTop = 0;
    return true;
  }
  function openSheet(i) {
    const E = state.els;
    if (!fillSheet(i)) return;
    state.sheetIndex = i;
    state.lastFocus = document.activeElement;
    E.scrim.hidden = false; E.sheet.hidden = false;
    E.sheet.style.transform = "";
    const show = () => { E.scrim.classList.add("open"); E.sheet.classList.add("open"); if (E.sheetClose.focus) E.sheetClose.focus(); };
    if (root.requestAnimationFrame) root.requestAnimationFrame(show); else show();
  }
  function closeSheet() {
    const E = state.els;
    if (state.sheetIndex < 0) return false;
    state.sheetIndex = -1;
    E.scrim.classList.remove("open"); E.sheet.classList.remove("open"); E.sheet.style.transform = "";
    setTimeout(() => { if (state.sheetIndex < 0) { E.scrim.hidden = true; E.sheet.hidden = true; } }, SHEET_CLOSE_MS);
    if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
    return true;
  }

  // ---------- events ----------
  function onPress(card, on) { if (card && card.classList) card.classList.toggle("pressing", on); }
  function onHold(card) {
    try { if (root.navigator && root.navigator.vibrate) root.navigator.vibrate(VIBRATE_MS); } catch (e) { /* no vibration */ }
    openSheet(Number(card.getAttribute("data-i")));
  }
  function wireEvents() {
    const E = state.els, hold = createHold({ onHold, onPress });
    state.hold = hold;
    E.seg.addEventListener("click", e => { const b = e.target && e.target.closest ? e.target.closest("[data-period]") : null; if (b) setPeriod(b.getAttribute("data-period")); });
    E.track.addEventListener("pointerdown", e => {
      const card = e.target && e.target.closest ? e.target.closest(".cardx") : null;
      if (!card || card.classList.contains("empty") || (e.pointerType === "mouse" && e.button !== 0)) return;
      hold.down(e.clientX, e.clientY, card);
    });
    root.addEventListener("pointermove", e => hold.move(e.clientX, e.clientY));
    root.addEventListener("pointerup", () => hold.up());
    root.addEventListener("pointercancel", () => hold.cancel());
    E.track.addEventListener("scroll", () => {
      hold.cancel();
      const w = E.track.clientWidth;
      if (w) setIndex(Math.round(E.track.scrollLeft / w));
      if (state.index > 0) hideHint();
    }, { passive: true });
    E.track.addEventListener("click", e => {
      if (hold.suppressClick()) { if (e.preventDefault) e.preventDefault(); return; }
      const b = e.target && e.target.closest ? e.target.closest("[data-go]") : null;
      if (b) go(Number(b.getAttribute("data-go")) - 1);
    });
    E.track.addEventListener("contextmenu", e => {
      const card = e.target && e.target.closest ? e.target.closest(".cardx") : null;
      if (!card) return;
      if (e.preventDefault) e.preventDefault();
      if (!hold.heldRecently() && !card.classList.contains("empty")) { hold.cancel(); openSheet(Number(card.getAttribute("data-i"))); }
    });
    E.sheetClose.addEventListener("click", closeSheet);
    E.scrim.addEventListener("click", closeSheet);
    wireSheetDrag();
    document.addEventListener("keydown", onKey);
    root.addEventListener("hashchange", () => { const n = cardFromHash(); if (n !== null && state.cards.length) { closeSheet(); go(n); } });
    root.addEventListener("resize", () => { E.track.scrollLeft = state.index * (E.track.clientWidth || 0); });
  }
  function wireSheetDrag() {
    const E = state.els;
    let drag = null;
    E.grab.addEventListener("pointerdown", e => { drag = { y: e.clientY }; if (E.grab.setPointerCapture) try { E.grab.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ } E.sheet.style.transition = "none"; });
    E.grab.addEventListener("pointermove", e => { if (drag) E.sheet.style.transform = `translateY(${Math.max(0, e.clientY - drag.y)}px)`; });
    const end = e => { if (!drag) return; E.sheet.style.transition = ""; const dy = e.clientY - drag.y; drag = null; if (dy > SHEET_DRAG_CLOSE_PX) closeSheet(); else E.sheet.style.transform = ""; };
    E.grab.addEventListener("pointerup", end);
    E.grab.addEventListener("pointercancel", end);
  }
  function onKey(e) {
    const E = state.els;
    if (state.sheetIndex >= 0) {
      if (e.key === "Escape") closeSheet();
      return;
    }
    if (e.key === "ArrowRight") go(state.index + 1);
    else if (e.key === "ArrowLeft") go(state.index - 1);
    else if (e.key === "Enter" && document.activeElement === E.track && state.cards.length) openSheet(state.index);
  }
  function hideHint() { const E = state.els; if (!E.hint.hidden) { E.hint.hidden = true; storeSet(STORE_HINTED, "1"); } }

  // ---------- loading ----------
  async function getJson(url) {
    try {
      const r = await root.fetch(url, { cache: "no-store" });
      if (!r || !r.ok) return null;
      return await r.json();
    } catch (e) { return null; }
  }
  function cleanMeta(m) {
    const o = obj(m);
    return { savedAt: typeof o.savedAt === "string" ? o.savedAt : null, offline: o.offline === true, error: typeof o.error === "string" && o.error.trim() ? o.error.trim() : null };
  }
  function reportProblem(r) {
    const o = obj(r);
    if (!r || typeof r !== "object") return EMPTY_TEXT;
    if (o.schema !== SCHEMA) return isNum(o.schema) && o.schema > SCHEMA ? "This report needs a newer version of the app." : EMPTY_TEXT;
    const p = obj(o.periods);
    return PERIODS.every(k => p[k] && typeof p[k] === "object") ? null : EMPTY_TEXT;
  }

  async function boot() {
    buildShell();
    const stored = storeGet(STORE_PERIOD);
    state.period = PERIODS.includes(stored) ? stored : "day";
    const [report, meta] = await Promise.all([getJson(DATA_URL), getJson(META_URL)]);
    state.meta = cleanMeta(meta);
    showMeta();
    const problem = reportProblem(report);
    if (problem) { showMessage(problem); return false; }
    state.report = report;
    const n = cardFromHash();
    state.index = n === null ? 0 : n;
    try {
      render();
    } catch (e) {
      if (root.console) root.console.error("DSE Report: render failed", e);
      showMessage("The saved report could not be shown. It will be replaced by the next download.");
      return false;
    }
    if (root.requestAnimationFrame) root.requestAnimationFrame(() => { state.els.track.scrollLeft = state.index * (state.els.track.clientWidth || 0); });
    if (!storeGet(STORE_HINTED) && state.index === 0) { state.els.hint.hidden = false; setTimeout(hideHint, HINT_MS); }
    return true;
  }

  root.DSEReport = {
    ready: null,
    createHold, go, setPeriod, openSheet, closeSheet,
    back: closeSheet,                     // for the shell's back button: true when it closed the sheet
    state: () => ({ period: state.period, index: state.index, count: state.cards.length, sheetOpen: state.sheetIndex >= 0, sheetIndex: state.sheetIndex }),
    format: { num, signed, pct, dayLabel, clockTime },
    constants: { HOLD_MS, MOVE_TOL, BASE_CARDS, EMPTY_TEXT },
  };
  root.DSEReport.ready = boot();
})(typeof window !== "undefined" ? window : globalThis);
