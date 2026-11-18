"use strict";
// Renders the bundled UI (android/app/src/main/assets/ui/app.js) against the report fixture in a minimal DOM stub.
// Run from the repo root: node android/ui-test/render.test.js   (no npm packages)
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const UI = path.join(__dirname, "..", "app", "src", "main", "assets", "ui");
const APP_JS = fs.readFileSync(path.join(UI, "app.js"), "utf8");
const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "latest.json"), "utf8"));
// New-shape write-ups (docs/WHY-CONTRACT.md) laid over the fixture: setups[i].view and periods[p].views, by index.
const VIEWS = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "views.json"), "utf8"));
const MARKET_KEYS = ["summary", "trend", "flow", "sectors", "signals"];
const MARK = { up: "✓", down: "✗", flat: "–" };
const FORBIDDEN = /\bundefined\b|\bNaN\b|\bnull\b|\[object/;
const EMPTY_TEXT = "No report saved yet. It downloads after 16:50 on trading days.";

// ---------- minimal DOM ----------
function makeDom() {
  const doc = { activeElement: null, listeners: {} };
  class Node {
    constructor() { this.childNodes = []; this.parentNode = null; this.listeners = {}; }
    appendChild(c) {
      if (!c || typeof c !== "object" || !(c instanceof Node)) throw new Error("appendChild: not a node: " + String(c));
      if (c.parentNode) c.parentNode.removeChild(c);
      c.parentNode = this; this.childNodes.push(c); return c;
    }
    removeChild(c) { const i = this.childNodes.indexOf(c); if (i >= 0) this.childNodes.splice(i, 1); c.parentNode = null; return c; }
    append(...cs) { cs.forEach(c => this.appendChild(typeof c === "string" ? new Text(c) : c)); }
    replaceChildren(...cs) { this.childNodes.slice().forEach(c => this.removeChild(c)); this.append(...cs); }
    get firstChild() { return this.childNodes[0] || null; }
    get textContent() { return this.childNodes.map(c => c.textContent).join(""); }
    set textContent(v) { this.replaceChildren(); if (v !== "" && v !== null && v !== undefined) this.appendChild(new Text(String(v))); }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter(x => x !== f); }
    dispatchEvent(ev) {
      ev.target = ev.target || this;
      for (let n = this; n; n = n.parentNode) (n.listeners[ev.type] || []).forEach(f => f.call(n, ev));
      return !ev.defaultPrevented;
    }
  }
  class Text extends Node {
    constructor(d) { super(); this.data = String(d); this.nodeType = 3; }
    get textContent() { return this.data; }
    set textContent(v) { this.data = String(v); }
  }
  class Element extends Node {
    constructor(tag, ns) {
      super(); this.localName = tag; this.tagName = tag.toUpperCase(); this.namespaceURI = ns || "http://www.w3.org/1999/xhtml";
      this.attrs = new Map(); this.style = {}; this.hidden = false; this.scrollLeft = 0; this.scrollTop = 0; this.clientWidth = 360; this.nodeType = 1;
    }
    setAttribute(k, v) { this.attrs.set(k, String(v)); }
    getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
    hasAttribute(k) { return this.attrs.has(k); }
    removeAttribute(k) { this.attrs.delete(k); }
    get className() { return this.getAttribute("class") || ""; }
    set className(v) { this.setAttribute("class", v); }
    get id() { return this.getAttribute("id") || ""; }
    get classList() {
      const el = this, list = () => el.className.split(/\s+/).filter(Boolean);
      const api = {
        add: (...c) => { el.className = [...new Set(list().concat(c))].join(" "); },
        remove: (...c) => { el.className = list().filter(x => !c.includes(x)).join(" "); },
        contains: c => list().includes(c),
        toggle: (c, force) => { const want = force === undefined ? !list().includes(c) : !!force; want ? api.add(c) : api.remove(c); return want; },
      };
      return api;
    }
    get children() { return this.childNodes.filter(c => c.nodeType === 1); }
    set innerHTML(v) { throw new Error("innerHTML must not be used"); }
    get innerHTML() { throw new Error("innerHTML must not be used"); }
    set outerHTML(v) { throw new Error("outerHTML must not be used"); }
    insertAdjacentHTML() { throw new Error("insertAdjacentHTML must not be used"); }
    matches(sel) { return sel.split(",").some(one => matchOne(this, one.trim())); }
    closest(sel) { for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(sel)) return n; return null; }
    querySelectorAll(sel) { const out = []; walk(this, n => { if (n !== this && n.nodeType === 1 && n.matches(sel)) out.push(n); }); return out; }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    focus() { doc.activeElement = this; }
    scrollTo(o) { if (o && typeof o === "object" && typeof o.left === "number") this.scrollLeft = o.left; }
    setPointerCapture() {}
  }
  function matchOne(el, sel) {
    const m = /^([a-zA-Z][\w-]*)?((?:[.#][\w-]+)*)((?:\[[^\]]+\])*)$/.exec(sel);
    if (!m) throw new Error("selector not supported by stub: " + sel);
    if (m[1] && el.localName !== m[1]) return false;
    for (const part of (m[2].match(/[.#][\w-]+/g) || [])) {
      if (part[0] === "." && !el.classList.contains(part.slice(1))) return false;
      if (part[0] === "#" && el.id !== part.slice(1)) return false;
    }
    for (const a of (m[3].match(/\[[^\]]+\]/g) || [])) {
      const am = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(a);
      if (!el.hasAttribute(am[1]) || (am[2] !== undefined && el.getAttribute(am[1]) !== am[2])) return false;
    }
    return true;
  }
  function walk(n, f) { f(n); n.childNodes.forEach(c => walk(c, f)); }
  const body = new Element("body");
  const appRoot = new Element("div"); appRoot.setAttribute("id", "app"); body.appendChild(appRoot);
  Object.assign(doc, {
    body, readyState: "complete",
    createElement: t => new Element(t),
    createElementNS: (ns, t) => new Element(t, ns),
    createTextNode: t => new Text(t),
    getElementById: id => { let f = null; walk(body, n => { if (!f && n.nodeType === 1 && n.id === id) f = n; }); return f; },
    addEventListener(t, fn) { (doc.listeners[t] = doc.listeners[t] || []).push(fn); },
    dispatch(ev) { (doc.listeners[ev.type] || []).forEach(fn => fn(ev)); },
  });
  return { doc, walk, Element };
}

// ---------- run the app in a fresh context ----------
function response(status, data) {
  return { ok: status >= 200 && status < 300, status, json: async () => (typeof data === "function" ? data() : data) };
}
async function runApp({ report, meta, hash = "", store = {}, fetchThrows = false, badJson = false }) {
  const { doc, walk } = makeDom();
  const listeners = {};
  const vibrations = [];
  const sandbox = {
    document: doc, console, setTimeout, clearTimeout, Promise, Date, Math, JSON,
    location: { hash },
    navigator: { vibrate: ms => { vibrations.push(ms); return true; } },
    localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    matchMedia: () => ({ matches: false }),
    requestAnimationFrame: f => f(),
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
    fetch: async url => {
      if (fetchThrows) throw new TypeError("Failed to fetch");
      if (url === "/data/latest.json") return report === undefined ? response(404) : response(200, badJson ? () => { throw new SyntaxError("bad json"); } : JSON.parse(JSON.stringify(report)));
      if (url === "/data/meta.json") return meta === undefined ? response(404) : response(200, meta);
      return response(404);
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(APP_JS, sandbox, { filename: "app.js" });
  const ok = await sandbox.DSEReport.ready;
  const fire = (type, ev) => (listeners[type] || []).forEach(f => f(ev));
  const track = doc.body.querySelector("main");
  const sheet = doc.body.querySelector("[role]") && doc.body.querySelectorAll("div").find(d => d.getAttribute("role") === "dialog");
  return { ok, doc, walk, api: sandbox.DSEReport, track, sheet, fire, store, vibrations, sandbox };
}

// ---------- checks ----------
function allText(node, walk) {
  const parts = [];
  walk(node, n => {
    if (n.nodeType === 3) parts.push(n.data);
    if (n.nodeType === 1) n.attrs.forEach((v, k) => parts.push(`${k}=${v}`));
  });
  return parts.join("\n");
}
function assertClean(text, where) {
  const m = FORBIDDEN.exec(text);
  if (m) {
    const at = text.indexOf(m[0]);
    assert.fail(`${where}: forbidden "${m[0]}" near: ${JSON.stringify(text.slice(Math.max(0, at - 80), at + 40))}`);
  }
}
function assertLinks(root, where) {
  root.querySelectorAll("a").forEach(a => {
    const href = a.getAttribute("href") || "";
    assert.ok(href.startsWith("https://"), `${where}: link not https: ${href}`);
    assert.strictEqual(a.getAttribute("target"), "_blank", `${where}: link target`);
    assert.strictEqual(a.getAttribute("rel"), "noopener noreferrer", `${where}: link rel`);
  });
  root.querySelectorAll("img").forEach(() => assert.fail(`${where}: an <img> was created from data`));
  root.querySelectorAll("script").forEach(() => assert.fail(`${where}: a <script> was created from data`));
}
const nSheet = r => r.sheet.querySelector(".body");

let passed = 0, failed = 0;
async function test(name, fn) {
  try { await fn(); passed++; console.log("  ok  " + name); } catch (e) { failed++; console.log("  FAIL " + name + "\n       " + (e && e.stack ? e.stack.split("\n").slice(0, 3).join("\n       ") : e)); }
}

async function renderEverything(report, label) {
  const expected = 5 + (report.setups || []).length + 2;
  let sheets = 0;
  for (const p of ["day", "week", "month"]) {
    const r = await runApp({ report, meta: { savedAt: "2026-11-18T15:48:00+06:00", offline: false, error: null }, store: { "dser-period": p } });
    assert.strictEqual(r.ok, true, `${label}/${p}: boot`);
    assert.strictEqual(r.api.state().period, p, `${label}/${p}: stored period used`);
    assert.strictEqual(r.track.children.length, expected, `${label}/${p}: card count`);
    assert.strictEqual(r.api.state().count, expected);
    assertClean(allText(r.doc.body, r.walk), `${label}/${p} cards`);
    assertLinks(r.doc.body, `${label}/${p} cards`);
    for (let i = 0; i < expected; i++) {
      r.api.openSheet(i);
      assert.strictEqual(r.api.state().sheetIndex, i);
      assert.strictEqual(r.sheet.hidden, false, "sheet visible");
      const body = nSheet(r);
      assert.ok(body.textContent.length > 40, `${label}/${p} sheet ${i + 1} has a write-up`);
      assertClean(allText(r.sheet, r.walk), `${label}/${p} sheet ${i + 1}`);
      assertLinks(r.sheet, `${label}/${p} sheet ${i + 1}`);
      const text = allText(r.sheet, r.walk);
      assert.ok(!/\bTerms\b/.test(text), `${label}/${p} sheet ${i + 1}: no "Terms"`);
      const st = (report.setups || [])[i - 5];
      const view = i < 5 ? ((report.periods[p].views || {})[MARKET_KEYS[i]]) : st && st.view;
      if (isNewView(view)) assertView(r, view, i < 5 ? "Levels" : "Plan", `${label}/${p} sheet ${i + 1}`);
      else if (i < 5 && (report.periods[p].summary.answers || []).some(a => a.card === i + 1)) {
        assert.ok(text.includes("Why?"), `${label}/${p} sheet ${i + 1}: Why? from the answers`);
      }
      sheets++;
      r.api.closeSheet();
    }
  }
  return sheets;
}

const isNewView = v => !!(v && (v.verdict || v.thesis || (v.pillars || []).length));
// The write-up as the contract lays it out: verdict box, Thesis, Why? marks per pillar, Plan / Levels tiles,
// What would change our view, then the card's detail below the divider.
function assertView(r, v, title, where) {
  const body = nSheet(r), text = body.textContent, block = body.querySelector("section.view");
  assert.ok(block, `${where}: view block`);
  const order = ["verdict", "thesis", "pillars", "plan", "change_view"].filter(k => (Array.isArray(v[k]) ? v[k].length : v[k]));
  const heads = { verdict: v.verdict, thesis: "Thesis", pillars: "Why?", plan: title, change_view: "What would change our view" };
  let at = -1;
  for (const k of order) {
    const pos = text.indexOf(heads[k]);
    assert.ok(pos > at, `${where}: "${heads[k]}" shown and in order`);
    at = pos;
  }
  if (v.verdict) assert.strictEqual(block.querySelector(".verdict").querySelector(".vtext").textContent, v.verdict, `${where}: verdict`);
  if (v.badge) assert.strictEqual(block.querySelector(".badge").textContent, v.badge, `${where}: badge`);
  if (v.tone) assert.ok(block.querySelector(".verdict").classList.contains(v.tone), `${where}: badge tone`);
  if (v.thesis) assert.ok(text.includes(v.thesis), `${where}: thesis text`);
  const rows = block.querySelectorAll("tr").filter(tr => tr.querySelector("td"));
  assert.strictEqual(rows.length, (v.pillars || []).length, `${where}: one row per pillar`);
  (v.pillars || []).forEach((pl, k) => {
    const tds = rows[k].children;
    assert.strictEqual(tds[0].textContent, MARK[pl.mark], `${where}: ${pl.name} mark`);
    assert.strictEqual(tds[1].textContent, pl.name, `${where}: pillar name`);
    assert.strictEqual(tds[2].textContent, pl.reading, `${where}: ${pl.name} reading`);
  });
  const tiles = block.querySelectorAll(".tile");
  assert.strictEqual(tiles.length, (v.plan || []).length, `${where}: one tile per ${title} entry`);
  (v.plan || []).forEach((t, k) => {
    const tt = tiles[k].textContent;
    assert.ok(tt.startsWith(t.label), `${where}: tile label ${t.label}`);
    if (typeof t.pct === "number") assert.ok(tt.endsWith(r.api.format.pct(t.pct)), `${where}: tile ${t.label} pct`);
    else assert.strictEqual(tiles[k].children.length, 2, `${where}: tile ${t.label} has no pct`);
  });
  if (v.plan_note) assert.ok(text.includes(v.plan_note), `${where}: plan note`);
  if (v.change_view) assert.strictEqual(block.querySelector("p.change").textContent, v.change_view, `${where}: change view`);
  if (v.method) assert.ok(text.includes(v.method), `${where}: method`);
  const hr = body.querySelector("hr.divider");
  assert.ok(hr && hr.parentNode.childNodes.indexOf(hr) === 1, `${where}: detail below a divider`);
  assert.ok(hr.parentNode.childNodes.length > 2, `${where}: card detail kept`);
  assert.ok(!text.includes("Our view") && !text.includes("Price targets"), `${where}: old analyst view gone`);
}
// The fixture with the new write-ups; the old-shape one with every new key removed.
function withViews(base) {
  const m = JSON.parse(JSON.stringify(base));
  (m.setups || []).forEach((st, i) => { if (VIEWS.setups[i]) st.view = JSON.parse(JSON.stringify(VIEWS.setups[i])); });
  for (const p of ["day", "week", "month"]) m.periods[p].views = JSON.parse(JSON.stringify(VIEWS.periods[p].views));
  return m;
}
function oldShape(base) {
  const m = JSON.parse(JSON.stringify(base));
  for (const p of ["day", "week", "month"]) delete m.periods[p].views;
  (m.setups || []).forEach(st => { const v = st.view || {}; ["badge", "tone", "verdict", "sub", "thesis", "pillars", "plan", "plan_note", "change_view"].forEach(k => delete v[k]); });
  return m;
}

function mutated() {
  const m = JSON.parse(JSON.stringify(FIXTURE));
  m.setups[0].target = null; m.setups[0].objective_if = null; m.setups[0].resistance = null; m.setups[0].pf_cols = null; m.setups[0].reasoning = null;
  m.setups[1].target = 30.5; m.setups[1].target_pct = 12.1;
  m.setups[2].conditions[0].help = null; m.setups[2].score = null; m.setups[2].close = null;
  m.records.forEach(r => { r.cash_yield_pct = null; });
  m.records[0].last_buy_label = null; m.records[0].record_date = null; m.records[0].dividend_text = null;
  m.records[1].can_still_buy = true; m.records[1].dividends = [{ kind: "cash", pct: 105, tk_per_share: 10.5 }]; m.records[1].dividend_text = "105% cash"; m.records[1].cash_yield_pct = 4.8;
  for (const p of ["day", "week", "month"]) {
    const P = m.periods[p];
    P.trend.ema200 = P.trend.ema200.map((v, i) => (i < 30 ? null : v));
    P.trend.ema20[5] = null; P.trend.macd.hist[0] = null; P.trend.macd.line = null;
    P.trend.last.ema200 = null; P.trend.last.dist_pct.ema200 = null; P.trend.cross = null; P.trend.macd_state.last_signal_cross = null;
    P.market.bp.path[3] = null; P.market.bp.reverse_at = null; P.market.pf.target = null; P.market.pf.pattern = null;
    P.flow.last14[2] = null; P.flow.vs_avg20 = null; P.flow.by_sector = null;
    P.signals.buys.forEach(b => { b.chips = null; b.chg_pct = null; b.mfi = null; });
    P.summary.answers[2].card = 99; P.summary.answers[3].state = null; P.summary.glance[1] = ["Up / down", null, null];
    P.sectors.highlights = [];
    P.news[0].move_pct = null; P.news[1].code = null;
    P.papers[0].link = "javascript:alert(1)"; P.papers[1].link = "http://insecure.example/x"; P.papers[2].title = '<img src=x onerror="alert(1)">';
  }
  delete m.periods.week.papers;
  m.periods.month.news = null;
  m.papersFailed = ["TBS stocks"];
  return m;
}

(async () => {
  console.log("render.test.js");

  await test("fixture: every period, every card and every sheet render clean", async () => {
    const sheets = await renderEverything(FIXTURE, "fixture");
    assert.strictEqual(sheets, 3 * (5 + FIXTURE.setups.length + 2));
  });

  await test("mutated fixture (nulls, missing papers, bad links, HTML in a headline) renders clean", async () => {
    await renderEverything(mutated(), "mutated");
    const r = await runApp({ report: mutated(), meta: undefined, store: { "dser-period": "day" } });
    const last = r.track.children[r.track.children.length - 1];
    assert.ok(last.textContent.includes('<img src=x onerror="alert(1)">'), "HTML in a headline shows as text");
    r.api.openSheet(r.track.children.length - 1);
    const text = nSheet(r).textContent;
    assert.ok(text.includes("Could not reach: TBS stocks"), "failed feeds listed");
    const hrefs = r.sheet.querySelectorAll("a").map(a => a.getAttribute("href"));
    assert.ok(!hrefs.some(h => /javascript:|http:\/\//.test(h)), "unsafe links not rendered");
    assert.ok(hrefs.length >= 1, "https links still rendered");
  });

  await test("new write-ups: every setup sheet and cards 1-5 show the verdict, Thesis, Why? marks, tiles, change view", async () => {
    const m = withViews(FIXTURE);
    await renderEverything(m, "views");
    for (const p of ["day", "week", "month"]) {
      const r = await runApp({ report: m, store: { "dser-period": p } });
      const n = 5 + m.setups.length;
      for (let i = 0; i < n; i++) {
        const v = i < 5 ? m.periods[p].views[MARKET_KEYS[i]] : m.setups[i - 5].view;
        r.api.openSheet(i);
        assertView(r, v, i < 5 ? "Levels" : "Plan", `views/${p} sheet ${i + 1}`);
        const text = nSheet(r).textContent;
        for (const want of ["Thesis", "Why?", "What would change our view", v.verdict, i < 5 ? "Levels" : "Plan"]) assert.ok(text.includes(want), `views/${p} sheet ${i + 1}: "${want}"`);
        const heads = nSheet(r).querySelectorAll("h4").map(x => x.textContent);
        assert.ok(heads.includes(i < 5 ? "Levels" : "Plan") && !heads.includes(i < 5 ? "Plan" : "Levels"), `views/${p} sheet ${i + 1}: tiles titled ${i < 5 ? "Levels" : "Plan"}`);
        r.api.closeSheet();
      }
      // records and headlines: no write-up
      for (const i of [n, n + 1]) { r.api.openSheet(i); assert.ok(!nSheet(r).querySelector("section.view"), `views/${p} sheet ${i + 1}: no view`); r.api.closeSheet(); }
    }
  });

  await test("MEGHNAPET sheet matches the mockup (B + A's thesis); front keeps the grade chip", async () => {
    const m = withViews(FIXTURE), r = await runApp({ report: m });
    const i = m.setups.findIndex(s => s.code === "MEGHNAPET");
    assert.ok(i >= 0);
    assert.ok(r.track.children[5 + i].textContent.includes("Grade A · Medium confidence"), "grade chip on the front");
    r.api.openSheet(5 + i);
    const body = nSheet(r), text = body.textContent;
    assert.strictEqual(body.querySelector(".badge").textContent, "A");
    assert.ok(text.includes("Buy on a close at 76.0") && text.includes("Medium confidence · 7 evidence points"));
    const marks = body.querySelector("section.view").querySelectorAll("td").filter(td => td.classList.contains("mark")).map(td => td.textContent).join("");
    assert.strictEqual(marks, "✓✓✓✓✓✓–");
    const tiles = body.querySelectorAll(".tile").map(t => t.textContent);
    assert.deepStrictEqual(tiles, ["Entry76.0+1.1%", "Target 180.0+6.4%", "Target 298.0+30.3%", "Stop64.0−14.9%"]);
    assert.ok(text.includes("Reward/risk 1.8 : 1. Main risk: a failed breakout that retests 75.0."));
    assert.ok(text.includes("A close below 72.1 (EMA50) before the trigger, or 64.0 (P&F sell) after it."));
    const mid = m.setups.findIndex(s => s.code === "MIDLANDBNK");
    r.api.openSheet(5 + mid);
    assert.ok(nSheet(r).textContent.includes("Buy on a close at 18.0, half size"));
    assert.ok(nSheet(r).querySelectorAll("td").some(td => td.textContent === "✗"), "a pillar against shows ✗");
  });

  await test("market levels: whole numbers without a decimal, counts with no pct", async () => {
    const m = withViews(FIXTURE), r = await runApp({ report: m });
    r.api.openSheet(1);
    assert.deepStrictEqual(nSheet(r).querySelectorAll(".tile").map(t => t.textContent), ["Reversal5,472−0.4%", "Next box5,504+0.1%", "Trend line5,688+3.5%"]);
    assert.strictEqual(nSheet(r).querySelector(".badge").textContent, "▲");
    r.api.openSheet(4);
    assert.deepStrictEqual(nSheet(r).querySelectorAll(".tile").map(t => t.textContent), ["Buys23", "Sells6"]);
  });

  await test("old-shape fixture (no views) renders through the fallbacks", async () => {
    const m = oldShape(FIXTURE);
    await renderEverything(m, "old");
    const r = await runApp({ report: m });
    for (let i = 0; i < 5 + m.setups.length; i++) {
      r.api.openSheet(i);
      const body = nSheet(r);
      assert.ok(!body.querySelector("section.view") && !body.querySelector("hr.divider"), `old sheet ${i + 1}: no view block`);
      if (i >= 5) assert.ok(body.textContent.includes("Cancel below") && body.textContent.includes("Point and figure"), `old setup sheet ${i + 1}: values and chart`);
      r.api.closeSheet();
    }
    r.api.openSheet(1);
    assert.ok(nSheet(r).textContent.includes("Why?"), "market card falls back to the answers' Why?");
  });

  await test("a view with fields missing or malformed skips those blocks silently", async () => {
    const m = withViews(FIXTURE);
    const d = m.periods.day.views;
    delete d.summary.thesis; d.summary.plan = null; d.summary.change_view = null; d.summary.method = null;
    d.trend.pillars = [{ name: "P&F", mark: "sideways", reading: null }, null, "x", { mark: "up" }]; d.trend.plan = [{ label: "Reversal", value: null }, { value: 3 }, null];
    d.flow = { verdict: "", thesis: "", pillars: [] };
    d.sectors.badge = null; d.sectors.tone = "weird"; d.sectors.sub = null;
    m.setups[0].view.verdict = null; m.setups[0].view.badge = null; m.setups[0].view.plan_note = null;
    m.setups[1].view = { grade: "B", confidence: "Medium" };
    for (const p of ["day"]) {
      const r = await runApp({ report: m, store: { "dser-period": p } });
      const n = 5 + m.setups.length + 2;
      for (let i = 0; i < n; i++) { r.api.openSheet(i); assertClean(allText(r.sheet, r.walk), `partial sheet ${i + 1}`); r.api.closeSheet(); }
      r.api.openSheet(0);
      let t = nSheet(r).textContent;
      assert.ok(!t.includes("Thesis") && !t.includes("Levels") && !t.includes("What would change our view") && t.includes("Why?"), "summary: only present blocks");
      r.api.openSheet(1);
      const rows = nSheet(r).querySelector("section.view").querySelectorAll("tr").filter(tr => tr.querySelector("td"));
      assert.strictEqual(rows.length, 1, "malformed pillars dropped");
      assert.strictEqual(rows[0].children[0].textContent, "–", "unknown mark shows as neutral");
      assert.ok(!nSheet(r).textContent.includes("Levels"), "no valid level tiles: no Levels heading");
      r.api.openSheet(2);
      assert.ok(!nSheet(r).querySelector("section.view"), "an empty view falls back");
      assert.ok(nSheet(r).textContent.includes("Why?"), "flow falls back to the answers");
      r.api.openSheet(3);
      assert.ok(nSheet(r).querySelector(".verdict").classList.contains("flat") && !nSheet(r).querySelector(".badge"), "no badge, neutral tone");
      r.api.openSheet(5);
      assert.ok(!nSheet(r).querySelector(".verdict") && nSheet(r).textContent.includes("Thesis"), "setup without verdict keeps the rest");
      r.api.openSheet(6);
      assert.ok(!nSheet(r).querySelector("section.view") && nSheet(r).textContent.includes("Cancel below"), "grade-only view falls back");
      assert.ok(r.track.children[6].textContent.includes("Grade B · Medium confidence"), "grade chip still on the front");
    }
  });

  await test("no setups: 7 cards, records and headlines still last", async () => {
    const m = JSON.parse(JSON.stringify(FIXTURE)); m.setups = [];
    const r = await runApp({ report: m });
    assert.strictEqual(r.track.children.length, 7);
    assert.ok(r.track.children[5].textContent.includes("Record dates") || r.track.children[5].textContent.toLowerCase().includes("record"));
  });

  await test("card numbers in the JSON match the card list", async () => {
    const r = await runApp({ report: FIXTURE });
    const kicks = r.track.children.map(c => c.querySelector(".kick").textContent);
    FIXTURE.setups.forEach(s => assert.ok(kicks[s.card - 1].startsWith("Watch"), `setup ${s.code} card ${s.card} is a setup card`));
    for (const p of ["day", "week", "month"]) FIXTURE.periods[p].summary.answers.forEach(a => assert.ok(a.card >= 1 && a.card <= kicks.length, `answer card ${a.card}`));
    assert.ok(kicks[1].startsWith("Trend") && kicks[2].startsWith("Money flow") && kicks[3].startsWith("Sectors") && kicks[4].startsWith("Signals"));
    assert.ok(kicks[kicks.length - 2].startsWith("Record dates") && kicks[kicks.length - 1].startsWith("Headlines"));
  });

  await test("deep link #card=N selects card N; hashchange moves; out of range clamps", async () => {
    for (const n of [1, 2, 6, 9, 11]) {
      const r = await runApp({ report: FIXTURE, hash: `#card=${n}` });
      assert.strictEqual(r.api.state().index, n - 1, `#card=${n}`);
      assert.strictEqual(r.track.children[n - 1].getAttribute("aria-current"), "true");
      assert.strictEqual(r.track.scrollLeft, (n - 1) * 360);
      assert.strictEqual(r.doc.body.querySelector(".prog").children.filter(i => i.className === "on").length, n);
    }
    const r = await runApp({ report: FIXTURE, hash: "#card=99" });
    assert.strictEqual(r.api.state().index, 10);
    r.sandbox.location.hash = "#card=3"; r.fire("hashchange", {});
    assert.strictEqual(r.api.state().index, 2);
  });

  await test("tapping an answer jumps to its card; period toggle is remembered", async () => {
    const r = await runApp({ report: FIXTURE });
    const btn = r.track.querySelectorAll("button").find(b => b.getAttribute("data-go") === "4");
    btn.dispatchEvent({ type: "click", target: btn, preventDefault() {} });
    assert.strictEqual(r.api.state().index, 3);
    const week = r.doc.body.querySelectorAll("button").find(b => b.getAttribute("data-period") === "week");
    week.dispatchEvent({ type: "click", target: week });
    assert.strictEqual(r.api.state().period, "week");
    assert.strictEqual(r.store["dser-period"], "week");
    assert.strictEqual(week.getAttribute("aria-pressed"), "true");
    assert.strictEqual(r.api.state().index, 3, "card kept on period change");
    assert.ok(r.track.children[0].textContent.includes("15–17 Nov"));
  });

  await test("hold 450 ms opens the sheet, vibrates, and the click after it is suppressed", async () => {
    const r = await runApp({ report: FIXTURE });
    const card = r.track.children[0].querySelector(".cardx");
    const btn = card.querySelectorAll("button").find(b => b.getAttribute("data-go") === "3");
    btn.dispatchEvent({ type: "pointerdown", target: btn, clientX: 50, clientY: 50, pointerType: "touch", button: 0 });
    assert.ok(card.classList.contains("pressing"));
    await new Promise(res => setTimeout(res, 520));
    assert.strictEqual(r.api.state().sheetOpen, true, "sheet open after hold");
    assert.deepStrictEqual(r.vibrations, [15]);
    assert.ok(!card.classList.contains("pressing"));
    r.fire("pointerup", {});
    btn.dispatchEvent({ type: "click", target: btn, preventDefault() {} });
    assert.strictEqual(r.api.state().index, 0, "click after hold suppressed");
    assert.strictEqual(r.api.back(), true, "back closes the sheet");
    assert.strictEqual(r.api.back(), false, "back with no sheet");
    btn.dispatchEvent({ type: "click", target: btn, preventDefault() {} });
    assert.strictEqual(r.api.state().index, 2, "next click works");
  });

  await test("gesture: hold timing, move tolerance, click suppression (fake clock)", async () => {
    const r = await runApp({ report: FIXTURE });
    let t = 0, timers = [], held = [], pressed = [];
    const clock = { now: () => t, setTimeout: (f, ms) => { timers.push({ f, at: t + ms }); return timers.length - 1; }, clearTimeout: id => { if (timers[id]) timers[id].f = null; } };
    const tick = ms => { t += ms; timers.forEach(x => { if (x.f && x.at <= t) { const f = x.f; x.f = null; f(); } }); };
    const g = r.api.createHold({ ...clock, onHold: x => held.push(x), onPress: (x, on) => pressed.push(on) });
    g.down(0, 0, "A"); tick(449); assert.deepStrictEqual(held, [], "not yet at 449 ms");
    tick(1); assert.deepStrictEqual(held, ["A"], "fires at 450 ms");
    assert.strictEqual(g.suppressClick(), true, "click right after a hold is suppressed");
    assert.strictEqual(g.suppressClick(), false, "only one click is suppressed");
    g.down(0, 0, "B"); g.move(6, 8); tick(500); assert.deepStrictEqual(held, ["A", "B"], "10 px move is within tolerance");
    tick(1000);
    g.down(0, 0, "C"); g.move(8, 7); tick(500); assert.deepStrictEqual(held, ["A", "B"], "move over 10 px cancels");
    g.down(0, 0, "D"); tick(200); g.up(); tick(500); assert.deepStrictEqual(held, ["A", "B"], "release before 450 ms is a tap");
    assert.strictEqual(g.suppressClick(), false, "a tap is not suppressed");
    g.down(0, 0, "E"); tick(450); tick(600); assert.strictEqual(g.suppressClick(), false, "suppression expires after 600 ms");
    assert.strictEqual(pressed[0], true, "press feedback starts on down");
  });

  await test("saved stamp and offline banner from meta.json", async () => {
    const r = await runApp({ report: FIXTURE, meta: { savedAt: "2026-11-18T09:48:00Z", offline: true, error: null } });
    const saved = r.doc.body.querySelector(".saved").textContent, bar = r.doc.body.querySelector(".offbar");
    assert.ok(/^Saved \d\d:\d\d · offline$/.test(saved), saved);
    assert.strictEqual(bar.hidden, false);
    assert.ok(bar.textContent.startsWith("Offline · showing the report saved at"));
    const r2 = await runApp({ report: FIXTURE, meta: { savedAt: null, offline: false, error: "HTTP 503" } });
    assert.strictEqual(r2.doc.body.querySelector(".saved").textContent, "");
    assert.ok(r2.doc.body.querySelector(".offbar").textContent.includes("HTTP 503"));
    const r3 = await runApp({ report: FIXTURE, meta: undefined });
    assert.strictEqual(r3.doc.body.querySelector(".offbar").hidden, true);
    assertClean(allText(r3.doc.body, r3.walk), "no meta");
  });

  await test("empty state: 404, network error, bad JSON, wrong schema", async () => {
    for (const opts of [{ report: undefined, meta: undefined }, { fetchThrows: true }, { report: FIXTURE, badJson: true }, { report: { schema: 1 } }, { report: { ...FIXTURE, schema: 0 } }]) {
      const r = await runApp(opts);
      assert.strictEqual(r.ok, false);
      assert.ok(r.doc.body.textContent.includes(EMPTY_TEXT), "empty text shown");
      assertClean(allText(r.doc.body, r.walk), "empty state");
      r.doc.dispatch({ type: "keydown", key: "ArrowRight" });
      r.doc.dispatch({ type: "keydown", key: "Enter" });
    }
    const r = await runApp({ report: { ...FIXTURE, schema: 2 } });
    assert.ok(r.doc.body.textContent.includes("newer version of the app"));
  });

  await test("index.html: CSP, local files only, no inline script or style", async () => {
    const html = fs.readFileSync(path.join(UI, "index.html"), "utf8");
    assert.ok(html.includes("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'"));
    assert.ok(!/<script>(?!\s*<\/script>)|<style|style="|https?:\/\//.test(html.replace(/http-equiv[^>]*>/, "")), "no inline code or remote URLs");
    const css = fs.readFileSync(path.join(UI, "app.css"), "utf8");
    assert.ok(!/@import|url\(\s*["']?https?:/.test(css), "no remote CSS");
    assert.ok(!/innerHTML|insertAdjacentHTML|outerHTML|document\.write|eval\(|new Function/.test(APP_JS), "no HTML-string APIs in app.js");
  });

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
