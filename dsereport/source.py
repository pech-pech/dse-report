"""Read everything the report needs from the engine, once, into plain JSON-able data (the "inputs").

This is the only module that touches the engine. Every other module is a pure function of these inputs, so they
test without a price store and without the engine's 35-second snapshot build.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from screeners import indicators as ind

DSEX = "00DSEX"
SERIES_BARS = 300        # DSEX and sector closes kept for EMA200 / MACD
STOCK_BARS = 60          # per-stock bars kept (MFI, squeeze, sketches)
DAILY_SESSIONS = 45      # per-session rows: a full month (22) plus the 20 sessions before it, with margin
PF_TAIL = 7              # P&F columns kept per stock
RESISTANCE_COLUMNS = 40  # columns searched for the nearest earlier X-column top above a pending buy trigger
EVENT_DAYS_BACK = 45
DIVIDEND_DAYS_BACK = 200   # declarations a later record-date notice may pair with (events.DIVIDEND_LOOKBACK_DAYS)


def _tail(seq, n):
    return [float(x) if x is not None else None for x in list(seq)[-n:]]


def _pf_tail(chart) -> dict:
    cols = chart.columns[-PF_TAIL:]
    lv = chart.scale.level
    return {"cols": [[c.direction, round(lv(c.lo), 4), round(lv(c.hi), 4), c.boxes] for c in cols],
            "reversal": chart.reversal}


def _pending(chart, buy_at) -> dict | None:
    """For a stock one box from a buy: the first column top above the trigger, and the vertical-count objective
    the buy would give if the current X column reaches the trigger (the engine's own formula: low + R x column size).
    """
    cols = chart.columns if chart is not None else []
    if not buy_at or len(cols) < 2 or cols[-1].direction != "X":
        return None
    sc, cur = chart.scale, cols[-1]
    top = sc.floor_box(buy_at)
    if top <= cur.hi:
        return None
    size = sum(sc.box_size(k) for k in range(cur.lo, top + 1))
    objective = sc.level(cur.lo) + chart.reversal * size
    above = [c.hi for c in cols[-RESISTANCE_COLUMNS:-1] if c.direction == "X" and c.hi > top]
    return {"objective": round(objective, 2), "resistance": round(sc.level(min(above)), 2) if above else None}


def _stock(code, st, inds, row, chart, info) -> dict:
    closes = list(st.close)
    e200 = ind.ema(closes, 200) if len(closes) >= 200 else [None]
    out = {
        "code": code, "sector": info[0] if info else row.get("sector"), "category": info[1] if info else row.get("category"),
        "dates": list(st.dates)[-STOCK_BARS:], "close": _tail(closes, STOCK_BARS), "high": _tail(st.high, STOCK_BARS),
        "low": _tail(st.low, STOCK_BARS), "volume": _tail(st.volume, STOCK_BARS),
        "ema200": e200[-1],
    }
    if inds is not None:
        for k in ("ema20", "ema50", "macd", "macd_signal", "macd_hist", "rsi", "adx", "rvol", "bandwidth"):
            out[k] = _tail(getattr(inds, k), STOCK_BARS)
    keep = ("signal", "pattern", "signal_date", "column", "boxes", "target", "stop", "buy_at", "sell_at", "to_buy",
            "to_sell", "rs_signal", "rs_column", "vol_ratio", "changed", "chg", "turnover", "trend", "stale")
    out.update({k: row.get(k) for k in keep})
    out["pf"] = _pf_tail(chart) if chart is not None else None
    out["pending"] = _pending(chart, row.get("buy_at")) if row.get("to_buy") == 1 else None
    return out


def _daily(con, sessions) -> list:
    """Per stock and session: close, previous close, volume, for the last DAILY_SESSIONS sessions (equities only)."""
    first = sessions[-(DAILY_SESSIONS + 1)]
    q = """SELECT ticker, date, close, volume,
                  LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev
           FROM prices WHERE date >= ? AND ticker NOT LIKE '00%' ORDER BY date"""
    keep = set(sessions[-DAILY_SESSIONS:])
    return [[t, d, c, p, v] for t, d, c, v, p in con.execute(q, (first,)) if d in keep]


def _events(con, asof) -> list:
    q = """SELECT code, kind, date, announced, value, detail, title FROM corp_events
           WHERE announced >= date(?, ?) OR date >= date(?, ?)
              OR (kind IN ('cash_dividend', 'stock_dividend') AND announced >= date(?, ?))
           ORDER BY announced, code"""
    back, div_back = f"-{EVENT_DAYS_BACK} day", f"-{DIVIDEND_DAYS_BACK} day"
    return [dict(zip(("code", "kind", "date", "announced", "value", "detail", "title"), r))
            for r in con.execute(q, (asof, back, asof, back, asof, div_back))]


def collect(db_path: str) -> dict[str, Any]:
    """Build the engine snapshot from ``db_path`` (read it through a copy if the store is live) and return the inputs."""
    from pnf_app.server import App  # imported here so the pure modules never import the engine

    app = App(db_path, scheduler=False)
    m = app.market
    snap = m.snapshot()
    home, market, sectors, screener = m.home(), m.market(), m.sectors(), m.screener()
    snap = m.snapshot()
    rows = {r["code"]: r for r in screener["rows"]}
    bdates, bcloses = snap["bench"]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    sessions = [d for (d,) in con.execute("SELECT DISTINCT date FROM prices WHERE ticker = ? ORDER BY date", (DSEX,))]
    page = m.chart(DSEX, days=730) or {}
    lv = lambda b: page["levels"][b - page["b0"]]  # noqa: E731  box index -> price
    cols = page.get("columns", [])[-PF_TAIL:]
    dsex_pf = {"cols": [[c["d"], lv(c["lo"]), lv(c["hi"]), c["hi"] - c["lo"] + 1] for c in cols], "reversal": 3} if cols else None
    stocks = {}
    for code, st in snap["stocks"].items():
        if code in rows:
            stocks[code] = _stock(code, st, snap["inds"].get(code), rows[code], snap["charts"].get(code), snap["info"].get(code))
    sec = snap["sectors"]
    return {
        "asof": snap["asof"],
        "sessions": sessions[-SERIES_BARS:],
        "dsex": {"dates": list(bdates)[-SERIES_BARS:], "close": _tail(bcloses, SERIES_BARS),
                 "pf": dsex_pf, "last_signal": page.get("last_signal"), "status": (page.get("status") or [None])[-1],
                 "objective": page.get("objective"), "action_points": page.get("action_points"),
                 "stops": page.get("stops"), "trend": page.get("trend"), "trend_level": page.get("trend_level"),
                 "chg1w": home["benchmark"].get("chg1w"), "chg1m": home["benchmark"].get("chg1m")},
        "market_bp": snap["bp"]["market"],
        "bp_series": [[x["date"], x["bp"]] for x in market["series"][-SERIES_BARS:]],
        "sector_bp": snap["bp"]["sectors"],
        "sector_rows": sectors["rows"],
        "home_sectors": home.get("sectors", []),
        "sector_series": {name: {"dates": list(s["dates"])[-SERIES_BARS:], "close": _tail(s["close"], SERIES_BARS),
                                 "members": list(s["members"])} for name, s in sec.items()},
        "breadth_today": market.get("breadth", {}),
        "regime": home.get("regime"),
        "stocks": stocks,
        "daily": _daily(con, sessions),
        "events": _events(con, snap["asof"]),
    }
