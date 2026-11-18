"""DSEX trend card: EMA20/50/200 and MACD over the last 60 sessions, with a headline and sentence from the numbers."""
from __future__ import annotations

from screeners import indicators as ind

from dsereport import fmt
from dsereport.periods import window

SHOW = 60                      # sessions drawn on the card
SLOPE_LOOKBACK = 5             # slope = last value vs this many sessions earlier
SPANS = (20, 50, 200)
KEYS = tuple(f"ema{n}" for n in SPANS)
PRICE_DIGITS = 2
MACD_DIGITS = 2
PCT_DIGITS = 2
COUNT_WORDS = {1: "one", 2: "two", 3: "three"}


def _r(v: float | None, d: int) -> float | None:
    return None if v is None else round(v, d)


def _rs(values: list, d: int) -> list:
    return [_r(v, d) for v in values]


def _slope(values: list) -> str | None:
    """'rising'/'falling'/'flat' for the last value vs SLOPE_LOOKBACK sessions earlier; None if either is missing."""
    if len(values) <= SLOPE_LOOKBACK:
        return None
    now, then = values[-1], values[-1 - SLOPE_LOOKBACK]
    if now is None or then is None:
        return None
    if now == then:
        return "flat"
    return "rising" if now > then else "falling"


def _dist_pct(close: float | None, avg: float | None) -> float | None:
    if close is None or not avg:
        return None
    return round((close / avg - 1) * 100, PCT_DIGITS)


def _hist_run(hist: list) -> int:
    """+N: the histogram rose for the last N sessions in a row; −N: fell; 0 if flat or unknown."""
    vals = [v for v in hist if v is not None]
    if len(vals) < 2:
        return 0
    step = vals[-1] - vals[-2]
    if step == 0:
        return 0
    sign, run = (1 if step > 0 else -1), 0
    for i in range(len(vals) - 1, 0, -1):
        d = vals[i] - vals[i - 1]
        if d == 0 or (d > 0) != (sign > 0):
            break
        run += 1
    return sign * run


def _last_cross(dates: list, a: list, b: list) -> tuple[str, str] | None:
    """The latest session where a moved above ('above') or below ('below') b, or None."""
    prev = None
    found = None
    for d, x, y in zip(dates, a, b):
        if x is None or y is None or x == y:
            continue
        side = x > y
        if prev is not None and side != prev:
            found = ("above" if side else "below", d)
        prev = side
    return found


def _headline(dist: dict) -> str:
    """From the signed distance of the close to each average (None = not enough history)."""
    have = [k for k in KEYS if dist.get(k) is not None]
    if not have:
        return "Not enough history for averages"
    above = [k for k in have if dist[k] > 0]
    below = [k for k in have if k not in above]
    n = len(have)
    total = {3: "all three", 2: "both available", 1: "the one available"}[n]
    noun = "average" if n == 1 else "averages"
    if not below:
        return f"Above {total} {noun}"
    if not above:
        return f"Below {total} {noun}"
    overhead = " and ".join(k.upper() for k in below)
    return f"Above {COUNT_WORDS[len(above)]} of {COUNT_WORDS[n]} averages; {overhead} overhead"


def _avg_phrase(key: str, last: dict) -> str:
    d = last["dist_pct"][key]
    word = "above" if d > 0 else "below"
    return f"{word} {key.upper()} ({fmt.num(last[key])}, {fmt.pct(d)})"


def _macd_phrase(state: dict) -> str:
    if state["above_signal"] is None:
        return "MACD has not enough history yet"
    sig = "above" if state["above_signal"] else "below"
    zero = "above" if state["above_zero"] else "below"
    text = f"MACD is {sig} its signal line and {zero} zero"
    run = state["hist_run"]
    if run:
        s = "" if abs(run) == 1 else "s"
        text += f", histogram {'rising' if run > 0 else 'falling'} {abs(run)} session{s}"
    return text


def _sentence(last: dict, state: dict) -> str:
    if last["close"] is None:
        return "No DSEX closes to measure."
    parts = [_avg_phrase(k, last) for k in KEYS if last["dist_pct"][k] is not None]
    missing = [k.upper() for k in KEYS if last["dist_pct"][k] is None]
    text = f"DSEX closed at {fmt.num(last['close'])}"
    if parts:
        text += ", " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0])
    if missing:
        text += f" ({' and '.join(missing)} not available yet: not enough history)"
    return f"{text}; {_macd_phrase(state)}."


def _macd_state(dates: list, line: list, sig: list, hist: list) -> dict:
    lv, sv = line[-1] if line else None, sig[-1] if sig else None
    cross = _last_cross(dates, line, sig)
    return {
        "above_signal": None if lv is None or sv is None else lv > sv,
        "above_zero": None if lv is None else lv > 0,
        "hist_run": _hist_run(hist),
        "last_signal_cross": {"kind": cross[0], "date": cross[1]} if cross else None,
    }


def _last(close: list, emas: dict) -> dict:
    c = close[-1] if close else None
    last = {"close": _r(c, PRICE_DIGITS)}
    last.update({k: _r(emas[k][-1] if emas[k] else None, PRICE_DIGITS) for k in KEYS})
    last["dist_pct"] = {k: _dist_pct(c, emas[k][-1] if emas[k] else None) for k in KEYS}
    last["slope"] = {k: _slope(emas[k]) for k in KEYS}
    return last


def trend_block(I: dict, p: str) -> dict:
    """The trend card for period p (the chart is always the last SHOW sessions; p sets period_sessions)."""
    dsex = I.get("dsex") or {}
    closes, dates = list(dsex.get("close") or []), list(dsex.get("dates") or [])
    full = {f"ema{n}": ind.ema(closes, n) for n in SPANS}
    line, sig, hist = ind.macd(closes) if closes else ([], [], [])
    cut = slice(-SHOW, None)
    d60, c60 = dates[cut], closes[cut]
    e60 = {k: v[cut] for k, v in full.items()}
    l60, s60, h60 = line[cut], sig[cut], hist[cut]
    last = _last(closes, full)
    state = _macd_state(d60, l60, s60, h60)
    cross = _last_cross(d60, e60["ema20"], e60["ema50"])
    return {
        "dates": d60,
        "close": _rs(c60, PRICE_DIGITS),
        **{k: _rs(v, PRICE_DIGITS) for k, v in e60.items()},
        "macd": {"line": _rs(l60, MACD_DIGITS), "signal": _rs(s60, MACD_DIGITS), "hist": _rs(h60, MACD_DIGITS)},
        "last": last,
        "cross": {"kind": f"EMA20 {cross[0]} EMA50", "date": cross[1]} if cross else None,
        "macd_state": state,
        "period_sessions": len(window(list(I.get("sessions") or []), p)),
        "headline": _headline(last["dist_pct"]),
        "sentence": _sentence(last, state),
    }
