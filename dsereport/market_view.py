"""The "Why?" view on each market card (summary, trend, flow, sectors, signals) for one report period.

Built only from the period's own blocks (see build._period); every word comes from their numbers by the rules
below, so two identical periods always read the same. See docs/WHY-CONTRACT.md, "Market cards".

Each card scores 3-5 pillars: "up" (for), "down" (against), "flat" (neutral). A pillar whose inputs are missing is
left out; a card with fewer than MIN_PILLARS pillars has no view (None). Badge: ▲ when more pillars are up than
down, ▼ when more are down, ◆ otherwise.
"""
from __future__ import annotations

from dsereport import fmt
from dsereport.brief import PERIOD_WORDS
from dsereport.display import sector_name

CARDS = ("summary", "trend", "flow", "sectors", "signals")
MIN_PILLARS = 3
MAX_VERDICT = 48
BADGES = {"up": "▲", "down": "▼", "flat": "◆"}
METHOD = "Rules-based reading of the period's numbers. Not investment advice."
MIDLINE = 50.0            # bullish percent midline
IN_LINE_PCT = 1.0         # turnover within ±1% of its 20-session average reads "in line"
BROAD = 2.0               # advancers at least twice decliners (or the reverse) reads "broad"
VOLUME_RATIO = 2.0        # heavy volume threshold, as signals.VOLUME_RATIO (not imported: it loads the engine)
BEATING_UP_SHARE = 0.25   # beating DSEX: up when at least this share of the stocks traded
BEATING_DOWN_SHARE = 0.10  # ... down below this share
LEVEL_PCT_DIGITS = 2
AVERAGES = ("ema20", "ema50", "ema200")


# ---- shared helpers ------------------------------------------------------

def _g(d, *keys):
    """Nested get that tolerates None anywhere on the path."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _cr(v: float) -> str:
    return f"Tk {fmt.num(abs(v), 0 if abs(v) >= 10 else 1)} crore"


def _cmp(a, b) -> str:
    return "up" if a > b else "down" if a < b else "flat"


def _pillar(name: str, mark: str, reading: str) -> dict:
    return {"name": name, "mark": mark, "reading": reading}


def _level(label: str, value, close, tone: str) -> dict | None:
    if value is None:
        return None
    pct = round((value / close - 1) * 100, LEVEL_PCT_DIGITS) if close else None
    return {"label": label, "value": value, "pct": pct, "tone": tone}


def _tone(pillars: list) -> str:
    up = sum(p["mark"] == "up" for p in pillars)
    down = sum(p["mark"] == "down" for p in pillars)
    return _cmp(up, down)


def _fit(*candidates: str | None) -> str:
    """The first candidate that fits the verdict length (the last one is cut if none does)."""
    texts = [c for c in candidates if c]
    for t in texts:
        if len(t) <= MAX_VERDICT:
            return t
    return texts[-1][:MAX_VERDICT].rstrip(" ,;")


def _view(pillars: list, verdict: str, thesis: str, plan: list, plan_note: str | None, change_view: str) -> dict:
    tone = _tone(pillars)
    n_up = sum(p["mark"] == "up" for p in pillars)
    return {"badge": BADGES[tone], "tone": tone, "verdict": verdict, "sub": f"{n_up} of {len(pillars)} pillars up",
            "thesis": thesis, "pillars": pillars, "plan": [x for x in plan if x], "plan_note": plan_note,
            "change_view": change_view, "method": METHOD}


def _enough(pillars: list) -> list | None:
    kept = [p for p in pillars if p]
    return kept if len(kept) >= MIN_PILLARS else None


# ---- pillars shared by several cards -------------------------------------

def _breadth_reading(flow: dict) -> str:
    adv, dec, n = flow["adv"], flow["dec"], flow.get("sessions") or 1
    if n > 1:
        return f"{fmt.num(adv, 0)} advances, {fmt.num(dec, 0)} declines over {n} sessions"
    return f"{fmt.num(adv, 0)} up, {fmt.num(dec, 0)} down"


def _p_breadth(flow) -> dict | None:
    if _g(flow, "adv") is None or _g(flow, "dec") is None or not (flow["adv"] or flow["dec"]):
        return None
    return _pillar("Breadth", _cmp(flow["adv"], flow["dec"]), _breadth_reading(flow))


def _turnover_diff(flow) -> float | None:
    vs = _g(flow, "vs_avg20")
    return None if vs is None else (vs - 1) * 100


def _p_turnover(flow, name: str = "Turnover") -> dict | None:
    diff = _turnover_diff(flow)
    many = (_g(flow, "sessions") or 1) > 1
    amount = _g(flow, "turnover_avg_cr") if many else _g(flow, "turnover_cr")
    if diff is None or amount is None:
        return None
    head = _cr(amount) + (" a session" if many else "")
    if abs(diff) < IN_LINE_PCT:
        return _pillar(name, "flat", f"{head}, in line with the 20-session average")
    side = "above" if diff > 0 else "below"
    return _pillar(name, _cmp(diff, 0), f"{head}, {fmt.num(abs(diff), 0)}% {side} the 20-session average")


def _p_money(flow, name: str = "Money flow") -> dict | None:
    net = _g(flow, "net_cr")
    if net is None:
        return None
    if round(net, 1) == 0:
        return _pillar(name, "flat", "No net money flow")
    reading = f"Net {_cr(net)} {'in' if net > 0 else 'out'}"
    if _g(flow, "in_cr") is not None and _g(flow, "out_cr") is not None:
        reading += f": {_cr(flow['in_cr'])} in rising stocks, {_cr(flow['out_cr'])} in falling"
    return _pillar(name, _cmp(net, 0), reading)


def _bp_words(bp: dict) -> str:
    value, col = bp["value"], bp.get("column")
    side = "above" if value > MIDLINE else "below" if value < MIDLINE else "on"
    text = f"{fmt.num(value)}%, {side} the 50 midline"
    if col in ("X", "O"):
        text += f", {'rising (X' if col == 'X' else 'falling (O'} column)"
    return text


def _col_mark(col) -> str:
    return {"X": "up", "O": "down"}.get(col, "flat")


def _p_bp(market) -> dict | None:
    bp = _g(market, "bp")
    if not bp or bp.get("value") is None:
        return None
    return _pillar("Bullish %", _col_mark(bp.get("column")), _bp_words(bp))


def _p_signal_counts(signals, name: str) -> dict | None:
    c = _g(signals, "counts") or {}
    if c.get("buys") is None or c.get("sells") is None:
        return None
    return _pillar(name, _cmp(c["buys"], c["sells"]), f"{c['buys']} buy, {c['sells']} sell signals")


# ---- summary -------------------------------------------------------------

def _breadth_words(flow) -> str | None:
    adv, dec = _g(flow, "adv"), _g(flow, "dec")
    if adv is None or dec is None or not (adv or dec):
        return None
    if adv == dec:
        return "Even breadth"
    if adv > dec:
        return "Broad advance" if adv >= BROAD * dec else "More gainers than losers"
    return "Broad decline" if dec >= BROAD * adv else "More losers than gainers"


def _money_words(flow) -> str | None:
    net = _g(flow, "net_cr")
    if net is None:
        return None
    if round(net, 1) == 0:
        return "no net money flow"
    return f"money flowing {'in' if net > 0 else 'out'}"


def _index_words(market, pw: str) -> str | None:
    d = _g(market, "dsex") or {}
    chg, close = d.get("chg_pct"), d.get("close")
    if chg is None or close is None:
        return None
    if round(chg, 2) == 0:
        return f"DSEX was unchanged {pw} at {fmt.num(close)}"
    return f"DSEX {'rose' if chg > 0 else 'fell'} {fmt.num(abs(chg), 2)}% {pw} to {fmt.num(close)}"


def _summary_thesis(market, flow, pw: str, tone: str) -> str:
    parts = [x for x in (_index_words(market, pw), _breadth_clause(flow)) if x]
    first = (" with ".join(parts) if len(parts) == 2 else parts[0]) if parts else f"The market {pw}"
    net = _g(flow, "net_cr")
    if net is not None and round(net, 1) != 0:
        first += f", and a net {_cr(net)} went {'into rising' if net > 0 else 'into falling'} stocks"
    second = {"up": "We would keep backing confirmed signals while breadth and money flow stay positive.",
              "down": "We would stay defensive until breadth and money flow turn positive.",
              "flat": "We would wait for breadth and money flow to agree before acting."}[tone]
    return f"{first}. {second}"


def _breadth_clause(flow) -> str | None:
    adv, dec, n = _g(flow, "adv"), _g(flow, "dec"), _g(flow, "sessions") or 1
    if adv is None or dec is None:
        return None
    if n > 1:
        return f"{fmt.num(adv, 0)} advances and {fmt.num(dec, 0)} declines"
    return f"{fmt.num(adv, 0)} stocks up and {fmt.num(dec, 0)} down"


def _reversal_clause(market) -> str:
    pf = _g(market, "pf") or {}
    if pf.get("reverse_at") is None or pf.get("column") not in ("X", "O"):
        return ""
    return f", or a DSEX box at {fmt.num(pf['reverse_at'], 0)} that reverses the P&F column"


def _summary_change(market, tone: str) -> str:
    head = {"up": "More stocks falling than rising, with money flowing out",
            "down": "More stocks rising than falling, with money flowing in",
            "flat": "Breadth and money flow moving the same way"}[tone]
    return head + _reversal_clause(market) + "."


def summary_view(p: str, period: dict) -> dict | None:
    market, flow, signals = period.get("market"), period.get("flow"), period.get("signals")
    pillars = _enough([_p_breadth(flow), _p_bp(market), _p_money(flow), _p_turnover(flow),
                       _p_signal_counts(signals, "Signals")])
    if not pillars:
        return None
    tone = _tone(pillars)
    b, m = _breadth_words(flow), _money_words(flow)
    idx = _g(market, "dsex", "chg_pct")
    verdict = _fit(f"{b}, {m}" if b and m else None, b, m and m[:1].upper() + m[1:],
                   f"DSEX {fmt.pct(idx, 2)}" if idx is not None else "Mixed market")
    d = _g(market, "dsex") or {}
    plan = [_tile("DSEX close", d.get("close"), None, "acc"),
            _tile("Change", d.get("chg_pts"), d.get("chg_pct"), fmt.tone(d.get("chg_pct")))]
    return _view(pillars, verdict, _summary_thesis(market, flow, PERIOD_WORDS[p], tone), plan, None,
                 _summary_change(market, tone))


def _tile(label: str, value, pct, tone: str) -> dict | None:
    return None if value is None else {"label": label, "value": value, "pct": pct, "tone": tone}


# ---- trend ---------------------------------------------------------------

def _p_pf(market) -> dict | None:
    pf = _g(market, "pf") or {}
    status, col = pf.get("status"), pf.get("column")
    if status not in ("BUY", "SELL") or col not in ("X", "O"):
        return None
    mark = {("BUY", "X"): "up", ("SELL", "O"): "down"}.get((status, col), "flat")
    reading = f"{status.capitalize()} signal, {col} column"
    if pf.get("reverse_at") is not None:
        reading += f"; reversal {fmt.num(pf['reverse_at'], 0)}"
    return _pillar("P&F", mark, reading)


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _avg_names(keys: list[str]) -> str:
    """['ema20', 'ema50', 'ema200'] -> 'EMA20, 50 and 200'."""
    nums = [k[3:] for k in keys]
    return "EMA" + _join(nums)


def _p_averages(trend) -> dict | None:
    dist = _g(trend, "last", "dist_pct") or {}
    have = [k for k in AVERAGES if dist.get(k) is not None]
    if not have:
        return None
    above = [k for k in have if dist[k] > 0]
    below = [k for k in have if k not in above]
    if not below:
        return _pillar("Averages", "up", f"Above {_avg_names(above)}")
    if not above:
        return _pillar("Averages", "down", f"Below {_avg_names(below)}")
    return _pillar("Averages", "flat", f"Above {_avg_names(above)}; below {_avg_names(below)}")


def _p_momentum(trend) -> dict | None:
    ms = _g(trend, "macd_state") or {}
    if ms.get("above_signal") is None:
        return None
    reading = f"MACD {'above' if ms['above_signal'] else 'below'} signal"
    if ms.get("above_zero") is not None:
        reading += f", {'above' if ms['above_zero'] else 'below'} zero"
    run = ms.get("hist_run") or 0
    if run:
        reading += f"; histogram {'rising' if run > 0 else 'falling'} {abs(run)} session{'s' if abs(run) > 1 else ''}"
    return _pillar("Momentum", "up" if ms["above_signal"] else "down", reading)


def _p_trend_breadth(market, flow) -> dict | None:
    bp = _g(market, "bp") or {}
    if bp.get("column") not in ("X", "O"):
        return None
    word = "rising" if bp["column"] == "X" else "falling"
    reading = f"BP {fmt.num(bp['value'])} {word}" if bp.get("value") is not None else f"BP {word}"
    if _g(flow, "adv") is not None and _g(flow, "dec") is not None:
        up, down = ("adv", "dec") if (flow.get("sessions") or 1) > 1 else ("up", "down")
        reading = f"{fmt.num(flow['adv'], 0)} {up} / {fmt.num(flow['dec'], 0)} {down}; " + reading
    return _pillar("Breadth", _col_mark(bp["column"]), reading)


def _line(market) -> tuple[str, float] | None:
    pf = _g(market, "pf") or {}
    if pf.get("trend") not in ("bull", "bear") or pf.get("trend_level") is None:
        return None
    return pf["trend"], pf["trend_level"]


def _p_trend_line(market) -> dict | None:
    line = _line(market)
    if not line:
        return None
    if line[0] == "bull":
        return _pillar("Trend line", "up", f"Above the bullish support at {fmt.num(line[1], 0)}")
    return _pillar("Trend line", "down", f"Below the bearish resistance at {fmt.num(line[1], 0)}")


def _short_term(trend) -> str:
    """'up' above EMA20 with MACD above signal, 'down' below both, else 'mixed'."""
    d20 = _g(trend, "last", "dist_pct", "ema20")
    sig = _g(trend, "macd_state", "above_signal")
    if d20 is None or sig is None:
        return "mixed"
    if d20 > 0 and sig:
        return "up"
    return "down" if d20 < 0 and not sig else "mixed"


_TREND_VERDICT = {("up", "bear"): "Recovering, under resistance", ("up", "bull"): "Uptrend, above support",
                  ("up", None): "Trend up", ("down", "bull"): "Weakening, above support",
                  ("down", "bear"): "Downtrend, under resistance", ("down", None): "Trend down",
                  ("flat", "bull"): "Mixed, above support", ("flat", "bear"): "Mixed, under resistance",
                  ("flat", None): "Mixed trend"}

_TREND_HEAD = {"up": "Short-term trend has turned up", "down": "Short-term trend has turned down",
               "mixed": "Short-term trend is mixed"}


def _trend_thesis(market, short: str) -> str:
    line = _line(market)
    head = _TREND_HEAD[short]
    if not line:
        rev = _g(market, "pf", "reverse_at")
        tail = (f"We would treat a box at {fmt.num(rev, 0)} as the first test of it." if rev is not None
                else "We would wait for the averages and MACD to agree.")
        return f"{head}. {tail}"
    kind, lvl = line[0], fmt.num(line[1], 0)
    if kind == "bear":
        link = "but DSEX still sits" if short == "up" else "and DSEX sits"
        first = f"{head}, {link} below its P&F resistance line at {lvl}"
        second = ("We treat this as a recovery inside a downtrend until that line breaks." if short != "down"
                  else "We treat this as a downtrend until DSEX closes above that line.")
    else:
        link = "but DSEX still holds" if short == "down" else "and DSEX holds"
        first = f"{head}, {link} above its P&F support line at {lvl}"
        second = ("We treat this as a pullback inside an uptrend unless that line breaks." if short != "up"
                  else "We treat this as an uptrend while DSEX stays above that line.")
    return f"{first}. {second}"


def _trend_change(market, trend) -> str:
    pf, line = _g(market, "pf") or {}, _line(market)
    parts = []
    if pf.get("reverse_at") is not None and pf.get("column") in ("X", "O"):
        parts.append(f"A box at {fmt.num(pf['reverse_at'], 0)} reverses the P&F column")
    if line:
        verb, what = ("above", "resistance") if line[0] == "bear" else ("below", "support")
        parts.append(f"a close {verb} {fmt.num(line[1], 0)} breaks the {what} line")
    if not parts:
        e20 = _g(trend, "last", "ema20")
        return f"A close through EMA20 ({fmt.num(e20)})." if e20 is not None else "A change in the MACD signal."
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _trend_plan(market) -> list:
    pf, close = _g(market, "pf") or {}, _g(market, "dsex", "close")
    rising = pf.get("column") != "O"
    return [_level("P&F reversal", pf.get("reverse_at"), close, "down" if rising else "up"),
            _level("Next box", pf.get("next_box"), close, "up" if rising else "down"),
            _level("Trend line", pf.get("trend_level"), close, "flat")]


def _trend_note(market) -> str | None:
    pf, close = _g(market, "pf") or {}, _g(market, "dsex", "close")
    if pf.get("target") is None:
        return None
    note = f"P&F price objective {fmt.num(pf['target'], 0)}"
    if close:
        note += f" ({fmt.pct((pf['target'] / close - 1) * 100)})"
    if pf.get("stop") is not None:
        note += f"; P&F stop {fmt.num(pf['stop'], 0)}"
    return note + "."


def trend_view(p: str, period: dict) -> dict | None:
    market, trend, flow = period.get("market"), period.get("trend"), period.get("flow")
    pillars = _enough([_p_pf(market), _p_averages(trend), _p_momentum(trend), _p_trend_breadth(market, flow),
                       _p_trend_line(market)])
    if not pillars:
        return None
    line = _line(market)
    verdict = _TREND_VERDICT[(_tone(pillars), line[0] if line else None)]
    return _view(pillars, verdict, _trend_thesis(market, _short_term(trend)), _trend_plan(market),
                 _trend_note(market), _trend_change(market, trend))


# ---- flow ----------------------------------------------------------------

def _p_inflow_sessions(flow) -> dict | None:
    last = _g(flow, "last14")
    k = _g(flow, "inflow_sessions_14")
    if not last or k is None:
        return None
    n = len(last)
    return _pillar("Inflow sessions", _cmp(2 * k, n), f"Net inflow on {k} of the last {n} sessions")


def _flow_verdict(flow) -> str:
    m = _money_words(flow) or "Money flow unknown"
    m = m[:1].upper() + m[1:]
    diff = _turnover_diff(flow)
    if diff is None:
        return _fit(m)
    if abs(diff) < IN_LINE_PCT:
        return _fit(f"{m}, turnover in line with average", m)
    side = "above" if diff > 0 else "below"
    return _fit(f"{m}, turnover {fmt.num(abs(diff), 0)}% {side} average",
                f"{m}, turnover {fmt.num(abs(diff), 0)}% {side}", m)


def _flow_thesis(flow, pw: str, tone: str) -> str:
    net = _g(flow, "net_cr")
    if net is None or round(net, 1) == 0:
        first = f"There was no net money flow {pw}"
    else:
        first = f"A net {_cr(net)} went into {'rising' if net > 0 else 'falling'} stocks {pw}"
    k, last = _g(flow, "inflow_sessions_14"), _g(flow, "last14")
    if k is not None and last:
        first += f", with net inflow on {k} of the last {len(last)} sessions"
    second = {"up": "We would read this as buying interest while net flow stays positive.",
              "down": "We would wait for net flow to turn positive before adding.",
              "flat": "We would wait for flow and breadth to agree."}[tone]
    return f"{first}. {second}"


def _flow_change(flow, tone: str) -> str:
    last = _g(flow, "last14") or []
    half = len(last) // 2
    if tone == "down":
        tail = f", with inflow on more than {half} of the last {len(last)} sessions" if last else ""
        return f"Net money flowing in{tail}."
    tail = f", or inflow on {half} or fewer of the last {len(last)} sessions" if last else ""
    return f"Net money flowing out{tail}."


def _flow_note(flow) -> str | None:
    total, n = _g(flow, "turnover_cr"), _g(flow, "sessions") or 1
    if total is None:
        return None
    return f"Turnover {_cr(total)}" + (f" over {n} sessions." if n > 1 else ".")


def flow_view(p: str, period: dict) -> dict | None:
    flow = period.get("flow")
    pillars = _enough([_p_money(flow, "Net flow"), _p_inflow_sessions(flow),
                       _p_turnover(flow, "Turnover vs average"), _p_breadth(flow)])
    if not pillars:
        return None
    tone = _tone(pillars)
    net = _g(flow, "net_cr")
    plan = [_tile("Money in", _g(flow, "in_cr"), None, "up"), _tile("Money out", _g(flow, "out_cr"), None, "down"),
            _tile("Net", net, None, fmt.tone(net))]
    return _view(pillars, _flow_verdict(flow), _flow_thesis(flow, PERIOD_WORDS[p], tone), plan, _flow_note(flow),
                 _flow_change(flow, tone))


# ---- sectors -------------------------------------------------------------

def _ranked(sectors) -> list:
    rows = [r for r in _g(sectors, "rows") or [] if r.get("chg_pct") is not None]
    return sorted(rows, key=lambda r: r["chg_pct"], reverse=True)


def _named(r: dict) -> str:
    return f"{sector_name(r['sector'])} {fmt.pct(r['chg_pct'])}"


def _p_leader(ranked: list) -> dict | None:
    return _pillar("Leader", fmt.tone(ranked[0]["chg_pct"]), _named(ranked[0])) if ranked else None


def _p_laggard(ranked: list) -> dict | None:
    return _pillar("Laggard", fmt.tone(ranked[-1]["chg_pct"]), _named(ranked[-1])) if len(ranked) > 1 else None


def _p_x_columns(sectors) -> dict | None:
    cols = [r.get("bp_column") for r in _g(sectors, "rows") or [] if r.get("bp_column") in ("X", "O")]
    if not cols:
        return None
    x = cols.count("X")
    return _pillar("Sectors in X columns", _cmp(2 * x, len(cols)),
                   f"{x} of {len(cols)} sectors' bullish % in rising (X) columns")


def _top_flow(sectors) -> dict | None:
    rows = [r for r in _g(sectors, "rows") or [] if r.get("net_cr") is not None]
    return max(rows, key=lambda r: r["net_cr"]) if rows else None


def _p_top_flow(sectors) -> dict | None:
    top = _top_flow(sectors)
    if not top:
        return None
    net = top["net_cr"]
    if net <= 0:
        return _pillar("Money into the top sector", "down" if net < 0 else "flat",
                       f"No sector took in money; {sector_name(top['sector'])} lost the least ({_cr(net)})")
    return _pillar("Money into the top sector", "up", f"{sector_name(top['sector'])}, net {_cr(net)} in")


def _sectors_thesis(ranked: list, sectors, pw: str, tone: str) -> str:
    lead = sector_name(ranked[0]["sector"]) if ranked else None
    up = sum(r["chg_pct"] > 0 for r in ranked)
    first = f"{up} of {len(ranked)} sector indices rose {pw}"
    if len(ranked) > 1:
        first += f"; {_named(ranked[0])} led and {_named(ranked[-1])} lagged"
    top = _top_flow(sectors)
    flow_name = sector_name(top["sector"]) if top and top["net_cr"] > 0 else None
    if tone == "up" and lead:
        where = lead if flow_name in (None, lead) else f"{lead} and {flow_name}"
        second = f"We would look for setups in {where} while money keeps going in."
    elif tone == "down":
        second = "We would wait for more sectors to turn up before leaning on sector strength."
    else:
        second = f"We would favour {lead} and stay selective elsewhere." if lead else "We would stay selective."
    return f"{first}. {second}"


def _sectors_change(sectors, tone: str) -> str:
    top = _top_flow(sectors)
    name = sector_name(top["sector"]) if top and top["net_cr"] > 0 else None
    if tone == "down":
        return "More than half the sectors' bullish % turning to rising (X) columns."
    tail = f", or money leaving {name}" if name else ""
    return f"Half or fewer of the sectors' bullish % in rising (X) columns{tail}."


def sectors_view(p: str, period: dict) -> dict | None:
    sectors = period.get("sectors")
    ranked = _ranked(sectors)
    pillars = _enough([_p_leader(ranked), _p_laggard(ranked), _p_x_columns(sectors), _p_top_flow(sectors)])
    if not pillars:
        return None
    tone = _tone(pillars)
    up = sum(r["chg_pct"] > 0 for r in ranked)
    lead = sector_name(ranked[0]["sector"]) if ranked else None
    verdict = _fit(f"{up} of {len(ranked)} sectors up, {lead} leads" if lead else None,
                   f"{up} of {len(ranked)} sectors up")
    plan = [_tile(sector_name(r["sector"]), r["chg_pct"], r["chg_pct"], fmt.tone(r["chg_pct"])) for r in ranked[:2]]
    return _view(pillars, verdict, _sectors_thesis(ranked, sectors, PERIOD_WORDS[p], tone), plan, None,
                 _sectors_change(sectors, tone))


# ---- signals -------------------------------------------------------------

def _traded(flow) -> int | None:
    """Stocks traded per session in the period (advances + declines + unchanged, averaged)."""
    parts = [_g(flow, k) for k in ("adv", "dec", "unch")]
    if any(v is None for v in parts) or not _g(flow, "sessions"):
        return None
    return round(sum(parts) / flow["sessions"]) or None


def _p_beating(signals, flow) -> dict | None:
    k = _g(signals, "counts", "beating")
    if k is None:
        return None
    n = _traded(flow)
    if not n:
        return _pillar("Beating DSEX", "flat", f"{k} stocks beat DSEX with rising relative strength")
    share = round(k / n * 100)            # marked on the shown whole percent, so reading and mark agree
    mark = "up" if share >= BEATING_UP_SHARE * 100 else "down" if share < BEATING_DOWN_SHARE * 100 else "flat"
    return _pillar("Beating DSEX", mark, f"{k} stocks ({share}% of {n} traded) beat DSEX")


def _p_volume(signals, flow) -> dict | None:
    k = _g(signals, "counts", "volume")
    if k is None:
        return None
    if k == 0:
        return _pillar("Volume surge", "flat", f"No stock at {fmt.num(VOLUME_RATIO, 0)}× average volume")
    net = _g(flow, "net_cr")
    reading = f"{k} stocks at {fmt.num(VOLUME_RATIO, 0)}× average volume or more"
    if net is None or round(net, 1) == 0:
        return _pillar("Volume surge", "flat", reading)
    return _pillar("Volume surge", _cmp(net, 0), reading + f", with net money {'in' if net > 0 else 'out'}")


def _signals_thesis(signals, pw: str, tone: str) -> str:
    c = _g(signals, "counts") or {}
    first = f"{c.get('buys', 0)} stocks gave P&F buy signals and {c.get('sells', 0)} gave sell signals {pw}"
    if c.get("beating") is not None:
        first += f"; {c['beating']} beat DSEX with rising relative strength"
    second = {"up": "We would check the buy list for setups that also beat DSEX.",
              "down": "We would hold back on new buys while sells outnumber buys.",
              "flat": "We would act only on signals that also beat DSEX."}[tone]
    return f"{first}. {second}"


def signals_view(p: str, period: dict) -> dict | None:
    signals, flow = period.get("signals"), period.get("flow")
    pillars = _enough([_p_signal_counts(signals, "Buys vs sells"), _p_beating(signals, flow), _p_volume(signals, flow)])
    if not pillars:
        return None
    tone = _tone(pillars)
    c = _g(signals, "counts") or {}
    b, s = c.get("buys"), c.get("sells")
    verdict = _fit(f"{b} buy and {s} sell signals" if b is not None and s is not None else None, "Signals mixed")
    plan = [_tile("Buys", b, None, "up"), _tile("Sells", s, None, "down")]
    change = {"up": "Sell signals outnumbering buys, or fewer stocks beating DSEX.",
              "down": "Buy signals outnumbering sells, with more stocks beating DSEX.",
              "flat": "Buys and sells moving apart, with stocks beating DSEX confirming the side."}[tone]
    return _view(pillars, verdict, _signals_thesis(signals, PERIOD_WORDS[p], tone), plan, None, change)


# ---- all cards -----------------------------------------------------------

BUILDERS = {"summary": summary_view, "trend": trend_view, "flow": flow_view, "sectors": sectors_view,
            "signals": signals_view}


def views(p: str, period: dict) -> dict:
    """{card: view or None} for the period's five market cards, from the period dict build._period makes."""
    return {name: BUILDERS[name](p, period) for name in CARDS}
