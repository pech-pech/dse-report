"""Card 5: the stocks that signalled, beat DSEX or traded heavy volume in the period."""
from __future__ import annotations

from screeners import indicators as ind

from dsereport import periods

MAX_ITEMS = 5
VOLUME_RATIO = 2.0          # RVOL at or above this counts as heavy volume
MFI_PERIOD = 14
MFI_HIGH, MFI_LOW = 80.0, 20.0
SQUEEZE_FACTOR = 1.1        # bandwidth within 10% of its 60-bar low
LISTS = ("buys", "sells", "beating", "volume")


def _last(values):
    """The last value of a list, or None for an empty/missing list."""
    return values[-1] if values else None


def period_change(dates: list[str], closes: list[float], base: str | None) -> float | None:
    """Percent change of the last close vs the close on ``base``; None if the base is missing."""
    if not base or not closes or base not in dates:
        return None
    then = closes[dates.index(base)]
    if not then:
        return None
    return round((closes[-1] / then - 1) * 100, 2)


def _mfi(s: dict) -> float | None:
    try:
        v = _last(ind.mfi(s["high"], s["low"], s["close"], s["volume"], MFI_PERIOD))
    except (KeyError, TypeError, ZeroDivisionError):
        return None
    return round(v, 1) if v is not None else None


def _macd_chip(s: dict) -> dict | None:
    line, sig = _last(s.get("macd")), _last(s.get("macd_signal"))
    if line is None or sig is None:
        return None
    if line > sig:
        return {"text": "MACD ↑ signal", "tone": "up"}
    return {"text": "MACD ↓ signal", "tone": "down"}


def _ma_chip(s: dict) -> dict | None:
    close, e50, e200 = _last(s.get("close")), _last(s.get("ema50")), s.get("ema200")
    if close is None or e50 is None:
        return None
    above50 = close > e50
    if e200 is None:
        return {"text": "Above EMA50" if above50 else "Below EMA50", "tone": "up" if above50 else "down"}
    above200 = close > e200
    if above50 and above200:
        return {"text": "Above EMA50 & EMA200", "tone": "up"}
    if not above50 and not above200:
        return {"text": "Below EMA50 & EMA200", "tone": "down"}
    if above50:
        return {"text": "Above EMA50, below EMA200", "tone": "warn"}
    return {"text": "Below EMA50, above EMA200", "tone": "warn"}


def _mfi_chip(mfi: float | None) -> dict | None:
    if mfi is None:
        return None
    extreme = mfi >= MFI_HIGH or mfi <= MFI_LOW
    return {"text": f"MFI {round(mfi):d}", "tone": "warn" if extreme else "flat"}


def _squeeze_chip(s: dict) -> dict | None:
    bw = [v for v in (s.get("bandwidth") or []) if v is not None]
    if not bw or (s.get("bandwidth") or [None])[-1] is None:
        return None
    if bw[-1] <= SQUEEZE_FACTOR * min(bw):
        return {"text": "Squeeze", "tone": "warn"}
    return None


def chips(s: dict, mfi: float | None) -> list[dict]:
    """Short coloured tags: MACD vs signal, price vs averages, MFI, Bollinger squeeze."""
    parts = (_macd_chip(s), _ma_chip(s), _mfi_chip(mfi), _squeeze_chip(s))
    return [c for c in parts if c is not None]


def _item(s: dict, chg: float | None) -> dict:
    mfi = _mfi(s)
    rvol = s.get("vol_ratio")
    return {
        "code": s["code"], "sector": s.get("sector"), "close": _last(s.get("close")),
        "chg_pct": chg, "pattern": s.get("pattern"), "signal_date": s.get("signal_date"),
        "target": s.get("target") or None, "stop": s.get("stop"),
        "rvol": round(rvol, 2) if rvol is not None else None, "mfi": mfi,
        "chips": chips(s, mfi), "pf_cols": [list(c) for c in (s.get("pf") or {}).get("cols", [])],
    }


def _avg_rvol(s: dict, window: set[str]) -> float | None:
    vals = [r for d, r in zip(s.get("dates", []), s.get("rvol") or []) if d in window and r is not None]
    return sum(vals) / len(vals) if vals else None


def _is_heavy(s: dict, window: set[str]) -> bool:
    if (s.get("vol_ratio") or 0) >= VOLUME_RATIO:
        return True
    avg = _avg_rvol(s, window)
    return avg is not None and avg >= VOLUME_RATIO


def _by_rvol(pairs: list) -> list:
    return sorted(pairs, key=lambda p: (-(p[0].get("vol_ratio") or 0), p[0]["code"]))


def _beating(pairs: list, dsex_chg: float | None) -> list:
    if dsex_chg is None:
        return []
    hits = [p for p in pairs if p[0].get("rs_column") == "X" and p[1] is not None and p[1] > dsex_chg]
    return sorted(hits, key=lambda p: (-p[1], p[0]["code"]))


def _pick(I: dict, period: str) -> dict:
    sessions = I["sessions"]
    win = set(periods.window(sessions, period))
    base = periods.base_session(sessions, period)
    pairs = [(s, period_change(s.get("dates", []), s.get("close", []), base))
             for s in I["stocks"].values()]
    dsex = I.get("dsex") or {}
    dsex_chg = period_change(dsex.get("dates", []), dsex.get("close", []), base)

    def signalled(kind):
        return [p for p in pairs if p[0].get("signal") == kind and p[0].get("signal_date") in win]

    return {
        "buys": _by_rvol(signalled("BUY")),
        "sells": _by_rvol(signalled("SELL")),
        "beating": _beating(pairs, dsex_chg),
        "volume": _by_rvol([p for p in pairs if _is_heavy(p[0], win)]),
    }


def signal_lists(I: dict, period: str) -> dict:
    """{buys, sells, beating, volume (top 5 items each), counts (full counts)} for the period."""
    picked = _pick(I, period)
    out = {k: [_item(s, chg) for s, chg in picked[k][:MAX_ITEMS]] for k in LISTS}
    out["counts"] = {k: len(picked[k]) for k in LISTS}
    return out
