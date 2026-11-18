"""Assemble the report JSON from the inputs: one block per period, plus the period-free setups and record dates."""
from __future__ import annotations

from datetime import datetime, timezone

from . import brief, display, events, flows, market, market_view, papers as papers_mod, periods, sectors, setups as setups_mod, signals, trend
from .schema import SCHEMA_VERSION

FIRST_SETUP_CARD = 6
SETUPS_SHOWN = 4


def _period(I: dict, p: str, setups: list, records: list, paper_feed: dict | None) -> dict:
    flow = flows.period_flow(I, p)
    mkt = market.market_block(I, p)
    tr = trend.trend_block(I, p)
    rows = sectors.sector_table(I, p, flow["by_sector"])
    sigs = signals.signal_lists(I, p)
    win = periods.window(I["sessions"], p)
    codes, names = list(I["stocks"]), [r["sector"] for r in rows]
    pp = papers_mod.select(paper_feed, win[0], win[-1], codes, names) if paper_feed and win else []
    out = {
        "label": periods.label(I["sessions"], p), "sessions": len(win),
        "summary": brief.summarize(p, mkt, tr, flow, rows, sigs, setups, records),
        "market": mkt, "trend": tr, "flow": flow,
        "sectors": {"rows": rows, "highlights": sectors.highlights(rows)},
        "signals": sigs, "news": events.company_news(I, p), "papers": pp,
    }
    return {**out, "views": market_view.views(p, out)}


def build_report(I: dict, paper_feed: dict | None = None, built_at: str | None = None) -> dict:
    """The whole report for the app. ``paper_feed`` is papers.fetch()'s result, or None to leave headlines out."""
    found = setups_mod.find_setups(I, k=SETUPS_SHOWN)
    cards = [{**s, "card": FIRST_SETUP_CARD + i} for i, s in enumerate(found)]
    records = events.record_dates(I)
    by_period = {p: _period(I, p, cards, records, paper_feed) for p in periods.PERIODS}
    return display.relabel({
        "schema": SCHEMA_VERSION,
        "asOf": I["asof"],
        "builtAt": built_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "periods": by_period,
        "setups": cards,
        "records": records,
        "notification": by_period["day"]["summary"]["notification"],
        "papersFetched": (paper_feed or {}).get("fetched_at"),
        "papersFailed": (paper_feed or {}).get("failed", []),
    })
