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


def _mfi_series(s: dict) -> list:
    try:
        return list(ind.mfi(s["high"], s["low"], s["close"], s["volume"], MFI_PERIOD))
    except (KeyError, TypeError, ZeroDivisionError):
        return []


def _mfi(s: dict) -> float | None:
    v = _last(_mfi_series(s))
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


RSI_LEVELS = (70.0, 50.0, 30.0)
MFI_LEVELS = (MFI_HIGH, 50.0, MFI_LOW)


def _direction(values) -> str | None:
    """"rising" / "falling" / "flat" from the last two non-missing values, or None."""
    vals = [v for v in (values or [])[-2:] if v is not None]
    if len(vals) < 2:
        return None
    return "rising" if vals[1] > vals[0] else "falling" if vals[1] < vals[0] else "flat"


def _band(v: float | None, levels: tuple) -> str | None:
    """Where v sits against (high, mid, low): ">high", ">mid", "<mid" or "<low" (mid itself counts as ">mid")."""
    if v is None:
        return None
    hi, mid, lo = (f"{x:g}" for x in levels)
    return f">{hi}" if v > levels[0] else f">{mid}" if v >= levels[1] else f"<{lo}" if v < levels[2] else f"<{mid}"


def _rsi_band(rsi: float | None) -> str | None:
    """Where RSI sits against 30 / 50 / 70: ">70", ">50", "<50" or "<30"."""
    return _band(rsi, RSI_LEVELS)


def _mfi_band(mfi: float | None) -> str | None:
    """Where MFI sits against 20 / 50 / 80: ">80", ">50", "<50" or "<20"."""
    return _band(mfi, MFI_LEVELS)


def state(s: dict) -> dict:
    """The one-line reading under a signal row: P&F column, MACD vs zero and its histogram's direction (vs the
    previous session), RSI and MFI bands and directions (vs the previous session)."""
    line = _last([v for v in (s.get("macd") or []) if v is not None])
    rsi_vals = s.get("rsi") or []
    rsi = _last([v for v in rsi_vals if v is not None])
    mfi_vals = _mfi_series(s)
    mfi = _last([v for v in mfi_vals if v is not None])
    return {"column": s.get("column") if s.get("column") in ("X", "O") else None,
            "macd": None if line is None else ("above" if line > 0 else "below"),
            "macd_dir": _direction(s.get("macd_hist")),
            "rsi": round(rsi, 1) if rsi is not None else None, "rsi_band": _rsi_band(rsi),
            "rsi_dir": _direction(rsi_vals),
            "mfi": round(mfi, 1) if mfi is not None else None, "mfi_band": _mfi_band(mfi), "mfi_dir": _direction(mfi_vals)}


def _item(s: dict, chg: float | None) -> dict:
    mfi = _mfi(s)
    rvol = s.get("vol_ratio")
    return {
        "code": s["code"], "sector": s.get("sector"), "close": _last(s.get("close")),
        "chg_pct": chg, "pattern": s.get("pattern"), "signal_date": s.get("signal_date"),
        "target": s.get("target") or None, "stop": s.get("stop"),
        "rvol": round(rvol, 2) if rvol is not None else None, "mfi": mfi,
        "chips": chips(s, mfi), "state": state(s), "pf_cols": [list(c) for c in (s.get("pf") or {}).get("cols", [])],
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
