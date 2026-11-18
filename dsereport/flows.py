"""Money flow: turnover (volume × close) split into money in rising, falling and unchanged stocks."""
from __future__ import annotations

from dsereport.periods import window

CRORE = 1e7              # Tk per crore
ROW_SESSIONS = 45        # sessions in session_rows: a full month plus the 20 before it
AVG_LOOKBACK = 20        # sessions before the period for vs_avg20
NET_SESSIONS = 14        # sessions in last14
OTHER_SECTOR = "Other"   # codes the stock table does not know
DIGITS = 2


def _valid(row) -> bool:
    return len(row) >= 5 and all(isinstance(v, (int, float)) for v in row[2:5])


def _side(close: float, prev: float) -> str:
    if close > prev:
        return "in"
    return "out" if close < prev else "flat"


def _rows_by_date(I: dict) -> dict:
    """{date: [(code, side, turnover_tk)]} from the valid `daily` rows."""
    out: dict = {}
    for row in I.get("daily", []):
        if not _valid(row):
            continue
        code, date, close, prev, volume = row[:5]
        out.setdefault(date, []).append((code, _side(close, prev), volume * close))
    return out


def _session(date: str, trades: list) -> dict:
    tk = {"in": 0.0, "out": 0.0, "flat": 0.0}
    n = {"in": 0, "out": 0, "flat": 0}
    for _code, side, value in trades:
        tk[side] += value
        n[side] += 1
    return {
        "date": date, "adv": n["in"], "dec": n["out"], "unch": n["flat"],
        "turnover_cr": round(sum(tk.values()) / CRORE, DIGITS),
        "in_cr": round(tk["in"] / CRORE, DIGITS),
        "out_cr": round(tk["out"] / CRORE, DIGITS),
        "flat_cr": round(tk["flat"] / CRORE, DIGITS),
        "net_cr": round((tk["in"] - tk["out"]) / CRORE, DIGITS),
    }


def session_rows(I: dict) -> list[dict]:
    """One row per session of the last ROW_SESSIONS in `daily`, oldest first."""
    by_date = _rows_by_date(I)
    dates = sorted(by_date)[-ROW_SESSIONS:]
    return [_session(d, by_date[d]) for d in dates]


def _sector_net(I: dict, dates: set) -> dict:
    """{sector: net Tk crore} over the given dates; codes without a sector go to 'Other'."""
    stocks = I.get("stocks", {})
    net: dict = {}
    for row in I.get("daily", []):
        if not _valid(row) or row[1] not in dates:
            continue
        code, _date, close, prev, volume = row[:5]
        sign = {"in": 1, "out": -1, "flat": 0}[_side(close, prev)]
        sector = (stocks.get(code) or {}).get("sector") or OTHER_SECTOR
        net[sector] = net.get(sector, 0.0) + sign * volume * close / CRORE
    return {k: round(v, DIGITS) for k, v in sorted(net.items())}


def _total(rows: list, key: str):
    return round(sum(r[key] for r in rows), DIGITS)


def _avg(rows: list):
    return sum(r["turnover_cr"] for r in rows) / len(rows) if rows else None


def _vs_avg(period_avg, before: list):
    base = _avg(before[-AVG_LOOKBACK:])
    if period_avg is None or not base:
        return None
    return round(period_avg / base, DIGITS)


def period_flow(I: dict, p: str) -> dict:
    """Breadth and money flow summed over the period's sessions, with the turnover ratio to the 20 before."""
    in_period = set(window(I.get("sessions", []), p))
    rows = session_rows(I)
    now = [r for r in rows if r["date"] in in_period]
    first = min(in_period) if in_period else ""
    before = [r for r in rows if r["date"] < first]
    avg = _avg(now)
    last14 = [r["net_cr"] for r in rows[-NET_SESSIONS:]]
    return {
        "sessions": len(now),
        "adv": sum(r["adv"] for r in now),
        "dec": sum(r["dec"] for r in now),
        "unch": sum(r["unch"] for r in now),
        "turnover_cr": _total(now, "turnover_cr"),
        "turnover_avg_cr": round(avg, DIGITS) if avg is not None else None,
        "vs_avg20": _vs_avg(avg, before),
        "in_cr": _total(now, "in_cr"),
        "out_cr": _total(now, "out_cr"),
        "flat_cr": _total(now, "flat_cr"),
        "net_cr": _total(now, "net_cr"),
        "last14": last14,
        "inflow_sessions_14": sum(1 for v in last14 if v > 0),
        "by_sector": _sector_net(I, {r["date"] for r in now}),
    }
