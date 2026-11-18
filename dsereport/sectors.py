"""Sector table for a report period and the three sector highlights (strongest, second, weakest)."""
from __future__ import annotations

from screeners import indicators as ind

from dsereport import fmt
from dsereport.periods import base_session

PCT_DIGITS = 2
CR_DIGITS = 2
SHARE_DIGITS = 1
HIGHLIGHT_COUNT = 3
MAX_REASONS = 4
ROW_FIELDS = ("bp", "bp_column", "bp_zone", "bp_signal", "rs_signal", "rs_column", "stocks", "score")


def _period_change(series: dict, base: str | None) -> float | None:
    """Last close of the sector index vs its close on the base session, in %."""
    dates, closes = series.get("dates") or [], series.get("close") or []
    if base is None or base not in dates or not closes:
        return None
    then, now = closes[dates.index(base)], closes[-1]
    if not then or now is None:
        return None
    return round((now / then - 1) * 100, PCT_DIGITS)


def _last(values: list | None):
    return values[-1] if values else None


def _above_ema50_pct(members: list[str], stocks: dict) -> float | None:
    """Share of members (with a close and an EMA50) whose last close is above their last EMA50."""
    above = counted = 0
    for code in members:
        s = stocks.get(code) or {}
        close, ema50 = _last(s.get("close")), _last(s.get("ema50"))
        if close is None or ema50 is None:
            continue
        counted += 1
        above += close > ema50
    return round(above / counted * 100, SHARE_DIGITS) if counted else None


def macd_state(closes: list[float]) -> str | None:
    """'above signal' / 'below signal' for the MACD of these closes; None when too short."""
    line, signal, _hist = ind.macd(list(closes))
    a, b = _last(line), _last(signal)
    if a is None or b is None:
        return None
    return "above signal" if a > b else "below signal"


def _row(src: dict, series: dict, base: str | None, stocks: dict, flow: dict) -> dict:
    sector = src["sector"]
    out = {"sector": sector, "chg_pct": _period_change(series, base)}
    out.update({k: src.get(k) for k in ROW_FIELDS})
    out["net_cr"] = round(float(flow.get(sector) or 0.0), CR_DIGITS)
    out["above_ema50_pct"] = _above_ema50_pct(series.get("members") or [], stocks)
    out["macd_state"] = macd_state(series.get("close") or [])
    return out


def sector_table(I: dict, p: str, flow_by_sector: dict) -> list[dict]:
    """One row per sector for period ``p``, sorted by the period change of its index (largest first)."""
    base = base_session(I["sessions"], p)
    all_series, stocks = I.get("sector_series") or {}, I.get("stocks") or {}
    rows = [_row(src, all_series.get(src["sector"]) or {}, base, stocks, flow_by_sector or {})
            for src in I.get("sector_rows") or []]
    known = sorted((r for r in rows if r["chg_pct"] is not None), key=lambda r: r["chg_pct"], reverse=True)
    return known + [r for r in rows if r["chg_pct"] is None]


# --- highlights -------------------------------------------------------------------------------------------------

def _move(r: dict) -> str:
    return f"Sector index {fmt.pct(r['chg_pct'])} over the period."


def _bp(r: dict) -> str | None:
    if r.get("bp") is None:
        return None
    way = "rising (X column)" if r.get("bp_column") == "X" else "falling (O column)"
    zone = f", {r['bp_zone']}" if r.get("bp_zone") else ""
    return f"Bullish % at {fmt.num(r['bp'])}%, {way}{zone}."


def _flow(r: dict) -> str:
    net = r.get("net_cr") or 0.0
    if net == 0:
        return "No net money flow (Tk 0 crore)."
    way = "in" if net > 0 else "out"
    return f"Net money flow Tk {fmt.num(abs(net))} crore {way}."


def _rs(r: dict) -> str | None:
    if r.get("rs_signal") not in ("BUY", "SELL"):
        return None
    col = "rising" if r.get("rs_column") == "X" else "falling"
    return f"Relative strength on a {r['rs_signal'].lower()} signal, column {col}."


def _breadth(r: dict) -> str | None:
    if r.get("above_ema50_pct") is None:
        return None
    return f"{fmt.num(r['above_ema50_pct'], 0)}% of its {r.get('stocks')} stocks close above their EMA50."


def _macd(r: dict) -> str | None:
    if not r.get("macd_state"):
        return None
    return f"Sector index MACD {r['macd_state']} line."


def _reasons(r: dict, weak: bool) -> list[str]:
    """3-4 short sentences built from the row's own numbers; the order favours what makes it strong or weak."""
    order = (_move, _bp, _flow, _breadth, _rs, _macd) if weak else (_move, _bp, _rs, _flow, _breadth, _macd)
    parts = [s for s in (f(r) for f in order) if s]
    return parts[:MAX_REASONS]


def _item(r: dict, weak: bool) -> dict:
    return {"sector": r["sector"], "chg_pct": r["chg_pct"], "tone": fmt.tone(r["chg_pct"]),
            "reasons": _reasons(r, weak)}


def highlights(rows: list[dict]) -> list[dict]:
    """The strongest and second sectors by period change, and the weakest (the last row)."""
    ranked = sorted((r for r in rows if r.get("chg_pct") is not None), key=lambda r: r["chg_pct"], reverse=True)
    if len(ranked) < HIGHLIGHT_COUNT:
        return [_item(r, weak=r["chg_pct"] < 0) for r in ranked]
    return [_item(ranked[0], False), _item(ranked[1], False), _item(ranked[-1], True)]
