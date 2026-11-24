"""The chart screen's data: one small JSON per stock the report names (P&F, RSI 14, MACD 12/26/9), as of the report.

Pure functions of the inputs ``I`` (``I["charts"]`` from ``source.collect``) and the built report. The P&F page is the
engine's own (box levels, columns with month marks, 45-degree trend lines); nothing here redraws or recounts it.
"""
from __future__ import annotations

import math
from typing import Any

from . import fmt

CHART_SCHEMA = 1
RSI_HIGH, RSI_LOW = 70, 30
MAX_MARK_LEN = 2
TREND_KINDS = ("bull", "bear")
DIRECTIONS = ("X", "O")
CHART_KEYS = ("schema", "code", "asOf", "sector", "header", "pf", "series", "reading")
SERIES_KEYS = ("dates", "close", "rsi", "macd", "signal", "hist")


def codes_in(report: Any, stocks: dict) -> list[str]:
    """Every stock code the report names under a ``code`` key, sorted: these are the codes the app makes links."""
    found: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            c = v.get("code")
            if isinstance(c, str) and c in stocks:
                found.add(c)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(report)
    return sorted(found)


def _last(values: list) -> float | None:
    for v in reversed(values or []):
        if v is not None:
            return v
    return None


def _r(v: float | None, d: int) -> float | None:
    return None if v is None or not math.isfinite(v) else round(float(v), d)


def _header(st: dict) -> dict:
    """The facts row: close, change, signal and the prices it turns on. ``reverse_at`` is the opposite signal's price."""
    buy = st.get("signal") == "BUY"
    return {"close": _r(_last(st.get("close")), 2), "chg": _r(st.get("chg"), 2), "signal": st.get("signal"),
            "pattern": st.get("pattern"), "signal_date": st.get("signal_date"), "column": st.get("column"),
            "target": _r(st.get("target"), 2), "stop": _r(st.get("stop"), 2),
            "reverse_at": _r(st.get("sell_at") if buy else st.get("buy_at"), 2),
            "rs_column": st.get("rs_column"), "rvol": _r(st.get("vol_ratio"), 1)}


def _series(ch: dict) -> dict:
    return {"dates": list(ch.get("dates") or []), "close": [_r(v, 2) for v in ch.get("close") or []],
            "rsi": [_r(v, 1) for v in ch.get("rsi") or []], "macd": [_r(v, 3) for v in ch.get("macd") or []],
            "signal": [_r(v, 3) for v in ch.get("macd_signal") or []],
            "hist": [_r(v, 3) for v in ch.get("macd_hist") or []]}


def _rsi_phrase(rsi: float | None) -> str | None:
    if rsi is None:
        return None
    where = "above 70" if rsi >= RSI_HIGH else "below 30" if rsi <= RSI_LOW else "between 30 and 70"
    return f"RSI {fmt.num(rsi, 0)} is {where}"


def _macd_phrase(line: float | None, sig: float | None) -> str | None:
    if line is None or sig is None:
        return None
    return f"MACD is {'above' if line >= sig else 'below'} its signal line and {'above' if line >= 0 else 'below'} zero"


def _reading(head: dict, series: dict) -> str:
    """One plain sentence from the numbers: the P&F state, then RSI and MACD. A reading, not advice."""
    parts = []
    if head["signal"] in ("BUY", "SELL"):
        kind = "buy" if head["signal"] == "BUY" else "sell"
        since = f" since {fmt.day(head['signal_date'])}" if head.get("signal_date") else ""
        parts.append(f"On a P&F {kind}{since}")
        if head["target"] and head["close"]:
            gap = (head["target"] / head["close"] - 1) * 100
            parts[-1] += f"; the target is {fmt.num(abs(gap), 0)}% {'above' if gap >= 0 else 'below'} the close"
    inds = [x for x in (_rsi_phrase(_last(series["rsi"])), _macd_phrase(_last(series["macd"]), _last(series["signal"]))) if x]
    if inds:
        parts.append("; ".join(inds))
    return (". ".join(parts) + ".") if parts else "Not enough history for a reading yet."


def stock_chart(I: dict, code: str) -> dict | None:
    """The chart file for one stock, or None when the inputs hold no chart for it."""
    st, ch = (I.get("stocks") or {}).get(code), (I.get("charts") or {}).get(code)
    if not st or not ch:
        return None
    head, series = _header(st), _series(ch)
    return {"schema": CHART_SCHEMA, "code": code, "asOf": I["asof"], "sector": st.get("sector"),
            "header": head, "pf": ch.get("pf"), "series": series, "reading": _reading(head, series)}


def build_charts(I: dict, report: dict) -> dict[str, dict]:
    """{code: chart} for every code the report names that has chart inputs."""
    out = {}
    for code in codes_in(report, I.get("stocks") or {}):
        c = stock_chart(I, code)
        if c is not None:
            out[code] = c
    return out


def _check_pf(pf: Any, errors: list[str], path: str) -> None:
    if pf is None:
        return
    if not isinstance(pf, dict) or not isinstance(pf.get("levels"), list) or not isinstance(pf.get("cols"), list):
        errors.append(f"{path}: expected levels and cols")
        return
    b0, top = pf.get("b0"), (pf.get("b0") or 0) + len(pf["levels"]) - 1
    for i, c in enumerate(pf["cols"]):
        if not (isinstance(c, list) and len(c) == 6 and c[0] in DIRECTIONS and isinstance(c[3], dict)):
            errors.append(f"{path}.cols[{i}]: expected [d, lo, hi, marks, start, end]")
        elif not (isinstance(b0, int) and b0 <= c[1] <= c[2] <= top):
            errors.append(f"{path}.cols[{i}]: boxes outside the levels")
        elif any(len(str(m)) > MAX_MARK_LEN for m in c[3].values()):
            errors.append(f"{path}.cols[{i}]: month mark too long")
    for i, t in enumerate(pf.get("trendlines") or []):
        if not (isinstance(t, dict) and t.get("kind") in TREND_KINDS):
            errors.append(f"{path}.trendlines[{i}]: unknown kind")


def validate_chart(chart: Any) -> list[str]:
    """Problems with one chart file as plain sentences; empty means it can be published."""
    from .schema import _walk  # the report's own finite-number and plain-type check

    errors: list[str] = []
    if not isinstance(chart, dict) or any(k not in chart for k in CHART_KEYS):
        return ["chart: missing keys"]
    path = f"chart {chart['code']}"
    s = chart["series"]
    if not isinstance(s, dict) or any(k not in s for k in SERIES_KEYS):
        errors.append(f"{path}.series: missing keys")
    elif len({len(s[k]) for k in SERIES_KEYS if s[k]}) > 1:
        errors.append(f"{path}.series: lists of different lengths")
    _check_pf(chart["pf"], errors, f"{path}.pf")
    _walk(chart, path, errors)
    return errors
