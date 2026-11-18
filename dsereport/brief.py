"""The report's top: verdict, lede, glance table, eight answers and the phone notification.

Built only from the other modules' outputs; every number and claim comes from them. Any input may be None or
empty: the matching wording then says the data is missing instead of guessing.
"""
from __future__ import annotations

from dsereport import fmt

PERIOD_WORDS = {"day": "today", "week": "this week", "month": "this month"}
FLAT_PCT = 0.05          # |DSEX change| below this (in %) reads as flat
THIN_TURNOVER = 0.8      # vs_avg20 below this: thin turnover
HEAVY_TURNOVER = 1.25    # vs_avg20 at or above this: heavy turnover
IN_LINE_PCT = 1.0        # turnover within ±1% of its average reads "in line"
NO_DATA = "No data"
CARD_PARTICIPATION, CARD_TREND, CARD_FLOW, CARD_SECTORS, CARD_SIGNALS, CARD_SETUP = 1, 2, 3, 4, 5, 6


# ---- small helpers -------------------------------------------------------

def _g(d: dict | None, *keys):
    """Nested get that tolerates None anywhere on the path."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _cr(v: float) -> str:
    return f"Tk {fmt.num(abs(v), 0 if abs(v) >= 10 else 1)} crore"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _vs_pct(flow: dict | None) -> float | None:
    vs = _g(flow, "vs_avg20")
    return None if vs is None else (vs - 1) * 100


def _vs_words(diff: float | None) -> str:
    if diff is None:
        return ""
    return ", in line with average" if abs(diff) < IN_LINE_PCT else f", {fmt.pct(diff, 0)} vs average"


def _direction(chg: float | None) -> str | None:
    if chg is None:
        return None
    if abs(chg) < FLAT_PCT:
        return "flat"
    return "up" if chg > 0 else "down"


def _answer(q: str, state: str, tone: str, detail: str, card: int | None) -> dict:
    return {"q": q, "state": state, "tone": tone, "detail": detail, "card": card}


def _missing(q: str, card: int | None) -> dict:
    return _answer(q, NO_DATA, "flat", "This data is not available for the period.", card)


def _sector_flows(sectors: list, flow: dict | None) -> list[tuple[str, float]]:
    rows = [(r["sector"], r["net_cr"]) for r in sectors or [] if r.get("net_cr") is not None]
    if not rows:
        rows = list((_g(flow, "by_sector") or {}).items())
    return sorted(rows, key=lambda kv: -kv[1])


# ---- verdict -------------------------------------------------------------

def _verdict(market: dict | None, flow: dict | None) -> str:
    move = _direction(_g(market, "dsex", "chg_pct"))
    if move is None:
        return "No index data"
    head = move.capitalize()
    net, vs = _g(flow, "net_cr"), _g(flow, "vs_avg20")
    if net:
        same = (net > 0) == (move == "up")
        link = "with" if move == "flat" or same else "but"
        return f"{head}, {link} money flowing {'in' if net > 0 else 'out'}"
    if vs is not None and vs < THIN_TURNOVER:
        return f"{head} on thin turnover"
    if vs is not None and vs >= HEAVY_TURNOVER:
        return f"{head} on heavy turnover"
    return head


# ---- lede ----------------------------------------------------------------

def _index_clause(market: dict | None, pw: str) -> str:
    dsex = _g(market, "dsex") or {}
    chg, pts, close = dsex.get("chg_pct"), dsex.get("chg_pts"), dsex.get("close")
    if chg is None or close is None:
        return f"No index data {pw}"
    if round(chg, 2) == 0:
        return f"DSEX was unchanged {pw} at {fmt.num(close)}"
    if abs(chg) < FLAT_PCT:
        return f"DSEX was little changed ({fmt.pct(chg, 2)}) {pw} at {fmt.num(close)}"
    verb = "rose" if chg > 0 else "fell"
    return f"DSEX {verb} {fmt.num(abs(pts or 0))} points ({fmt.pct(chg, 2)}) {pw} to {fmt.num(close)}"


def _turnover_clause(flow: dict | None) -> str:
    total = _g(flow, "turnover_cr")
    if total is None:
        return ""
    n = _g(flow, "sessions") or 1
    text = f", on turnover of {_cr(total)}"
    if n > 1 and _g(flow, "turnover_avg_cr") is not None:
        text += f" over {n} sessions ({_cr(flow['turnover_avg_cr'])} a session)"
    diff = _vs_pct(flow)
    if diff is None:
        return text
    if abs(diff) < IN_LINE_PCT:
        return text + ", in line with its 20-session average"
    side = "above" if diff > 0 else "below"
    return text + f", {fmt.num(abs(diff), 0)}% {side} its 20-session average"


def _flow_sentence(flow: dict | None) -> str:
    if not flow:
        return "No money flow or breadth data."
    parts = []
    net = flow.get("net_cr")
    if net is not None:
        head = "Money flow was even" if round(net) == 0 else \
            f"Money flow was a net {_cr(net)} {'in' if net > 0 else 'out'}"
        if flow.get("in_cr") is not None and flow.get("out_cr") is not None:
            head += f" ({_cr(flow['in_cr'])} traded in rising stocks, {_cr(flow['out_cr'])} in falling ones)"
        parts.append(head)
    if flow.get("adv") is not None and flow.get("dec") is not None:
        parts.append(_breadth_words(flow))
    return ("; ".join(parts) + ".") if parts else "No money flow or breadth data."


def _breadth_words(flow: dict) -> str:
    """One session counts stocks; several sessions count stock-days, so say advances and declines."""
    adv, dec, n = flow["adv"], flow["dec"], flow.get("sessions") or 1
    if n > 1:
        return f"{fmt.num(adv, 0)} advances and {fmt.num(dec, 0)} declines over {n} sessions"
    return f"{fmt.num(adv, 0)} stocks rose and {fmt.num(dec, 0)} fell"


def _ranked(sectors: list | None) -> list:
    """Sectors that have a change for the period (a short series has none and is never leader or laggard)."""
    return [s for s in sectors or [] if s.get("chg_pct") is not None]


def _leaders_sentence(sectors: list, sigs: dict | None, pw: str) -> str:
    parts = []
    sectors = _ranked(sectors)
    if len(sectors) >= 2:
        a, z = sectors[0], sectors[-1]
        parts.append(f"{a['sector']} led ({fmt.pct(a['chg_pct'])}) and {z['sector']} lagged ({fmt.pct(z['chg_pct'])})")
    elif sectors:
        parts.append(f"{sectors[0]['sector']} moved {fmt.pct(sectors[0]['chg_pct'])}")
    counts = _g(sigs, "counts")
    if counts:
        parts.append(f"there were {counts.get('buys', 0)} buy and {counts.get('sells', 0)} sell signals {pw}")
    if not parts:
        return "No sector or signal data."
    text = "; ".join(parts) + "."
    return text[0].upper() + text[1:]


def _lede(pw, market, flow, sectors, sigs) -> str:
    first = _index_clause(market, pw) + _turnover_clause(flow) + "."
    return " ".join([first, _flow_sentence(flow), _leaders_sentence(sectors, sigs, pw)])


# ---- glance --------------------------------------------------------------

def _glance(market: dict | None, flow: dict | None) -> list[list[str]]:
    dsex, bp, f = _g(market, "dsex") or {}, _g(market, "bp") or {}, flow or {}
    adv, dec, unch = f.get("adv"), f.get("dec"), f.get("unch")
    inflow = f.get("inflow_sessions_14")
    diff = _vs_pct(flow)
    bp_v, bp_0 = bp.get("value"), bp.get("start_value")
    return [
        ["DSEX", fmt.num(dsex.get("close")), fmt.pct(dsex.get("chg_pct"), 2)],
        ["Up / down" if (f.get("sessions") or 1) <= 1 else "Advances / declines", f"{fmt.num(adv, 0)} / {fmt.num(dec, 0)}" if adv is not None and dec is not None else "–",
         f"{unch} unchanged" if unch is not None else ""],
        ["Net money flow Tk cr", fmt.signed(f.get("net_cr"), 0),
         f"{inflow} of 14 sessions in" if inflow is not None else ""],
        ["Turnover Tk cr", fmt.num(f.get("turnover_cr"), 0),
         f"{fmt.pct(diff, 0)} vs avg" if diff is not None else ""],
        ["Bullish %", fmt.num(bp_v), f"{fmt.signed(bp_v - bp_0)} pts" if None not in (bp_v, bp_0) else ""],
    ]


# ---- the eight answers ---------------------------------------------------

_TREND_STATES = {("BUY", "X"): ("Yes", "up"), ("BUY", "O"): ("Buy signal, pulling back", "flat"),
                 ("SELL", "O"): ("No", "down"), ("SELL", "X"): ("Sell signal, bouncing", "flat")}


def _a_uptrend(market: dict | None) -> dict:
    q = "Is DSEX in an uptrend?"
    pf = _g(market, "pf") or {}
    key = (pf.get("status"), pf.get("column"))
    if key not in _TREND_STATES:
        return _missing(q, CARD_TREND)
    state, tone = _TREND_STATES[key]
    if key == ("BUY", "X") and pf.get("trend") == "bear":
        state, tone = "Buy signal, under the trend line", "flat"
    detail = f"P&F {key[0].lower()} signal"
    if pf.get("signal_date"):
        detail += f" since {fmt.day(pf['signal_date'])}"
    if pf.get("pattern"):
        detail += f": {pf['pattern']}"
    detail += f"; now in an {key[1]} column"
    if pf.get("next_box") is not None and pf.get("reverse_at") is not None:
        detail += f", next box {fmt.num(pf['next_box'])}, reversal at {fmt.num(pf['reverse_at'])}"
    if pf.get("trend") == "bear" and pf.get("trend_level") is not None:
        detail += f"; the bearish resistance line is at {fmt.num(pf['trend_level'], 0)}"
    return _answer(q, state, tone, detail + ".", CARD_TREND)


def _a_breadth(flow: dict | None, pw: str) -> dict:
    q = "Are most stocks rising?"
    adv, dec = _g(flow, "adv"), _g(flow, "dec")
    if adv is None or dec is None:
        return _missing(q, CARD_PARTICIPATION)
    state, tone = ("Yes", "up") if adv > dec else ("No", "down") if adv < dec else ("Evenly split", "flat")
    detail = f"{_breadth_words(flow)} {pw}"
    if flow.get("unch") is not None:
        detail += f"; {flow['unch']} were unchanged"
    return _answer(q, state, tone, detail + ".", CARD_PARTICIPATION)


def _a_oversold(market: dict | None) -> dict:
    q = "Is it oversold?"
    bp = _g(market, "bp") or {}
    zone, value = bp.get("zone"), bp.get("value")
    if not zone or value is None:
        return _missing(q, CARD_PARTICIPATION)
    low = zone.lower()
    state = "Yes" if low.startswith("oversold") else "No, overbought" if low.startswith("overbought") else "No"
    col = bp.get("column")
    tone = {"X": "up", "O": "down"}.get(col, "flat")
    detail = f"Bullish % is {fmt.num(value)} ({zone})"
    if col:
        detail += f", in an {col} column"
        if bp.get("column_since"):
            detail += f" since {fmt.day(bp['column_since'])}"
    if bp.get("reverse_at") is not None:
        detail += f"; it reverses at {fmt.num(bp['reverse_at'])}"
    return _answer(q, state, tone, detail + ".", CARD_PARTICIPATION)


def _a_money(sectors: list, flow: dict | None, pw: str) -> dict:
    q = "Where is money going?"
    rows = _sector_flows(sectors, flow)
    if not rows:
        return _missing(q, CARD_FLOW)
    (best, b_net), (worst, w_net) = rows[0], rows[-1]
    if b_net > 0:
        detail = f"Net {_cr(b_net)} went into {best} {pw}"
        if w_net < 0:
            detail += f"; most left {worst} ({_cr(w_net)})"
        return _answer(q, best, "up", detail + ".", CARD_FLOW)
    if w_net < 0:
        detail = f"No sector took in money {pw}; {worst} lost the most ({_cr(w_net)})."
        return _answer(q, "Out of every sector", "down", detail, CARD_FLOW)
    return _answer(q, "No net flow", "flat", f"No sector had a net flow {pw}.", CARD_FLOW)


def _a_momentum(trend: dict | None) -> dict:
    q = "Is momentum building?"
    ms = _g(trend, "macd_state") or {}
    above, run = ms.get("above_signal"), ms.get("hist_run")
    if above is None or run is None:
        return _missing(q, CARD_TREND)
    if above and run > 0:
        state, tone = "Yes", "up"
    elif not above and run < 0:
        state, tone = "No", "down"
    else:
        state, tone = "Mixed", "flat"
    detail = f"MACD is {'above' if above else 'below'} its signal line"
    if ms.get("above_zero") is not None:
        detail += f" and {'above' if ms['above_zero'] else 'below'} zero"
    if run:
        detail += f"; the histogram has been {'rising' if run > 0 else 'falling'} {_plural(abs(run), 'session')}"
    return _answer(q, state, tone, detail + ".", CARD_TREND)


def _a_leader(sectors: list, pw: str) -> dict:
    q = "Which sector leads?"
    sectors = _ranked(sectors)
    if not sectors:
        return _missing(q, CARD_SECTORS)
    top = sectors[0]
    detail = f"{top['sector']} {fmt.pct(top['chg_pct'])} {pw}"
    if top.get("bp") is not None:
        detail += f", bullish % {fmt.num(top['bp'])}"
        if top.get("bp_column"):
            detail += f" ({top['bp_column']} column)"
    if len(sectors) > 1:
        detail += f"; weakest {sectors[-1]['sector']} {fmt.pct(sectors[-1]['chg_pct'])}"
    return _answer(q, top["sector"], fmt.tone(top["chg_pct"]), detail + ".", CARD_SECTORS)


def _a_signals(sigs: dict | None, pw: str) -> dict:
    q = "What signalled?"
    counts = _g(sigs, "counts")
    if not counts:
        return _missing(q, CARD_SIGNALS)
    b, s = counts.get("buys", 0), counts.get("sells", 0)
    tone = "up" if b > s else "down" if b < s else "flat"
    detail = f"{b} new buy and {s} new sell signals {pw}"
    if counts.get("beating") is not None and counts.get("volume") is not None:
        detail += f"; {counts['beating']} stocks beating DSEX and {counts['volume']} on heavy volume"
    return _answer(q, f"{_plural(b, 'buy')} · {_plural(s, 'sell')}", tone, detail + ".", CARD_SIGNALS)


def _a_setups(setups: list) -> dict:
    q = "What may break out?"
    if not setups:
        return _answer(q, "None", "flat", "No stock is one box from a P&F buy.", None)
    top = setups[0]
    detail = f"{top['code']} is one box from a P&F buy at {fmt.num(top.get('trigger'))}"
    if top.get("score") is not None:
        detail += f" ({top['score']} of {len(top.get('conditions') or []) or 7} conditions met)"
    detail += "."
    if len(setups) > 1:
        detail += f" {len(setups) - 1} more on the list."
    return _answer(q, _plural(len(setups), "setup"), "flat", detail, CARD_SETUP)


# ---- notification --------------------------------------------------------

def _closing_line(market, sectors, setups, records) -> str | None:
    buyable = [r for r in records or [] if r.get("can_still_buy", True) and r.get("dividends")]
    if buyable:
        r = buyable[0]
        line = f"{r['code']} record date {r.get('label') or fmt.day(r['record_date'])}"
        line += f" ({r['dividend_text']})" if r.get("dividend_text") else ""
        return line + (f", buy by {r['last_buy_label']}" if r.get("last_buy_label") else "")
    if setups:
        return f"{setups[0]['code']} one box from a buy at {fmt.num(setups[0].get('trigger'))}"
    bp = _g(market, "bp") or {}
    return f"Bullish % {fmt.num(bp['value'])}, {bp.get('zone', '')}".rstrip(", ") if bp.get("value") is not None \
        else None


def _notification(market, flow, sectors, sigs, setups, records) -> dict:
    counts = _g(sigs, "counts") or {}
    title = (f"DSEX {fmt.pct(_g(market, 'dsex', 'chg_pct'), 2)} · {_plural(counts.get('buys', 0), 'buy')}"
             f" · {_plural(counts.get('sells', 0), 'sell')}")
    f, lines = flow or {}, []
    if f.get("turnover_cr") is not None:
        diff = _vs_pct(flow)
        lines.append(f"Turnover {_cr(f['turnover_cr'])}" + _vs_words(diff))
    if f.get("net_cr") is not None:
        lines.append("Money flow even" if round(f["net_cr"]) == 0 else
                     f"Money flow: net {_cr(f['net_cr'])} {'in' if f['net_cr'] > 0 else 'out'}")
    if f.get("adv") is not None and f.get("dec") is not None:
        lines.append(f"{f['adv']} up · {f['dec']} down")
    if sectors:
        lines.append(f"{sectors[0]['sector']} leads, {fmt.pct(sectors[0]['chg_pct'])}")
    last = _closing_line(market, sectors, setups, records)
    if last:
        lines.append(last)
    return {"title": title, "lines": lines[:5]}


# ---- public --------------------------------------------------------------

def summarize(p: str, market: dict | None, trend: dict | None, flow: dict | None, sectors: list | None,
              sigs: dict | None, setups: list | None, records: list | None) -> dict:
    """The report's summary card for period ``p`` from the other modules' outputs (see CONTRACT.md item 9)."""
    if p not in PERIOD_WORDS:
        raise ValueError(f"unknown period {p!r}")
    pw, sectors, setups, records = PERIOD_WORDS[p], sectors or [], setups or [], records or []
    answers = [_a_uptrend(market), _a_breadth(flow, pw), _a_oversold(market), _a_money(sectors, flow, pw),
               _a_momentum(trend), _a_leader(sectors, pw), _a_signals(sigs, pw), _a_setups(setups)]
    return {
        "verdict": _verdict(market, flow),
        "lede": _lede(pw, market, flow, sectors, sigs),
        "glance": _glance(market, flow),
        "answers": answers,
        "notification": _notification(market, flow, sectors, sigs, setups, records),
    }
