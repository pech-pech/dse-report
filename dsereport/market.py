"""Market card: DSEX move for the period, its P&F status, the bullish percent and the levels to watch."""
from __future__ import annotations

from dsereport import fmt
from dsereport.periods import base_session, label

PATH_LENGTH = 30          # bullish percent readings shown in the sparkline
MIDLINE = 50.0            # the bullish percent midline
PRICE_DIGITS = 2
PCT_DIGITS = 2
BP_DIGITS = 1


def _round(v: float | None, d: int) -> float | None:
    return None if v is None else round(float(v), d)


def _close_on(dates: list[str], closes: list[float], day: str | None) -> float | None:
    if day is None or day not in dates:
        return None
    return closes[dates.index(day)]


def _dsex(I: dict, base: str | None) -> dict:
    d = I.get("dsex") or {}
    dates, closes = d.get("dates") or [], d.get("close") or []
    last = closes[-1] if closes else None
    start = _close_on(dates, closes, base)
    if last is None or not start:
        return {"close": _round(last, PRICE_DIGITS), "chg_pts": None, "chg_pct": None}
    return {"close": _round(last, PRICE_DIGITS), "chg_pts": _round(last - start, PRICE_DIGITS),
            "chg_pct": _round((last / start - 1) * 100, PCT_DIGITS)}


def _pf(I: dict) -> dict:
    d = I.get("dsex") or {}
    ap = d.get("action_points") or {}
    sig = d.get("last_signal") or {}
    cols = (d.get("pf") or {}).get("cols") or []
    column = ap.get("column") or (cols[-1][0] if cols else None)
    return {"status": d.get("status"), "column": column, "pattern": sig.get("pattern"),
            "signal_date": sig.get("date"), "target": (d.get("objective") or {}).get("target"),
            "next_box": ap.get("next"), "reverse_at": ap.get("reverse"), "stop": (d.get("stops") or {}).get("stop"),
            "trend": d.get("trend"), "trend_level": d.get("trend_level")}


def _bp(I: dict, base: str | None) -> dict:
    mb = I.get("market_bp") or {}
    series = I.get("bp_series") or []
    by_day = {day: v for day, v in series}
    value = mb.get("bp", mb.get("reading"))
    return {"value": _round(value, BP_DIGITS), "column": mb.get("column"), "zone": mb.get("zone"),
            "signal": mb.get("signal"), "column_since": mb.get("column_since"),
            "reverse_at": _round(mb.get("reverse_at"), BP_DIGITS),
            "start_value": _round(by_day.get(base), BP_DIGITS),
            "path": [_round(v, BP_DIGITS) for _, v in series[-PATH_LENGTH:]]}


def _dsex_level(close: float | None, pf: dict) -> dict | None:
    nxt, rev, col = pf["next_box"], pf["reverse_at"], pf["column"]
    if close is None or nxt is None or rev is None or col not in ("X", "O"):
        return None
    if col == "X":
        text = (f"DSEX {fmt.num(close)} is in a rising X column: the next box up is {fmt.num(nxt, 0)}, "
                f"and a fall to {fmt.num(rev, 0)} would turn it to an O column.")
    else:
        text = (f"DSEX {fmt.num(close)} is in a falling O column: the next box is down to {fmt.num(nxt, 0)}, "
                f"and a rise to {fmt.num(rev, 0)} would turn it to an X column.")
    return {"label": "DSEX next box", "text": text}


def _pattern_name(pattern: str) -> str:
    """'Bullish Signal (Diagonal Triple Top)' -> 'a Diagonal Triple Top'."""
    inner = pattern[pattern.find("(") + 1:pattern.rfind(")")] if "(" in pattern and ")" in pattern else pattern
    return "a " + inner.strip()


def _target_level(pf: dict) -> dict | None:
    if not pf["status"]:
        return None
    text = f"The P&F status is {pf['status']}"
    if pf["pattern"]:
        text += f": {_pattern_name(pf['pattern'])}"
        text += f" on {fmt.day(pf['signal_date'])}" if pf["signal_date"] else ""
    if pf["target"]:
        text += f", with a price objective of {fmt.num(pf['target'], 0)}"
    return {"label": "P&F signal", "text": text + "."}


def _bp_level(bp: dict) -> dict | None:
    value, col = bp["value"], bp["column"]
    if value is None:
        return None
    side = "above" if value > MIDLINE else "below" if value < MIDLINE else "on"
    text = f"Bullish percent is {fmt.num(value)}%, {side} the 50 midline"
    if col in ("X", "O"):
        text += f", in a {'rising X' if col == 'X' else 'falling O'} column"
        if bp["column_since"]:
            text += f" since {fmt.day(bp['column_since'])}"
    if bp["reverse_at"] is not None and col in ("X", "O"):
        move, to = ("drop", "O") if col == "X" else ("rise", "X")
        text += f"; a {move} to {fmt.num(bp['reverse_at'])}% would reverse it to {to}"
    return {"label": "Bullish %", "text": text + "."}


def _stop_level(close: float | None, stop: float | None) -> dict | None:
    if close is None or not stop:
        return None
    gap = abs(close - stop) / close * 100
    side = "below" if stop <= close else "above"
    text = f"The P&F stop is at {fmt.num(stop, 0)}, {fmt.num(gap)}% {side} the close."
    return {"label": "Stop", "text": text}


def _levels(dsex: dict, pf: dict, bp: dict) -> list[dict]:
    items = [_dsex_level(dsex["close"], pf), _target_level(pf), _bp_level(bp), _stop_level(dsex["close"], pf["stop"])]
    return [x for x in items if x is not None]


def market_block(I: dict, p: str) -> dict:
    """The market card for period ``p``: DSEX change vs the session before the period, P&F, bullish percent."""
    sessions = I.get("sessions") or []
    base = base_session(sessions, p)        # raises ValueError for an unknown period
    regime = I.get("regime") or {}
    dsex, pf, bp = _dsex(I, base), _pf(I), _bp(I, base)
    return {"asof": I.get("asof"), "label": label(sessions, p), "dsex": dsex, "pf": pf, "bp": bp,
            "regime": {"name": regime.get("name"), "note": regime.get("note")},
            "levels": _levels(dsex, pf, bp)}
