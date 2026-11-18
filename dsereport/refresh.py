"""Bring a price store up to date through the engine's own refresh job (prices, bonus adjustments, sectors,
company news and corporate events), the same job the desktop app runs. Used by the daily cloud build.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date, timedelta

DSEX = "00DSEX"
JOB_TIMEOUT_S = 30 * 60
DECLARATION_DAYS_BACK = 200      # how far back a record date's dividend declaration may lie
MAX_ARCHIVES = 150               # company news histories fetched per run (one AmarStock request each, ~1 s)
ARCHIVE_DELAY_S = 1.0


def last_session(db_path: str) -> str | None:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
        return con.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (DSEX,)).fetchone()[0]


def _run(app, kind: str, **kw) -> dict:
    if not app.jobs.start(kind, **kw):
        raise RuntimeError(f"another {app.jobs.status().get('kind')} job is already running")
    app.jobs.wait(JOB_TIMEOUT_S)
    st = app.jobs.status()
    if st.get("running"):
        app.jobs.cancel()
        raise TimeoutError(f"{kind} did not finish in {JOB_TIMEOUT_S // 60} minutes")
    return st.get("last") or {"ok": False, "detail": "no result"}


def missing_declarations(db_path: str, after: str) -> list[str]:
    """Companies with a record date after ``after`` but no dividend declaration in the store before it.
    The daily news read covers a few sessions only, so a store seeded from an older snapshot misses the
    declarations made in between (the record date then arrives alone, in DSE's Spot News list)."""
    q = """SELECT DISTINCT r.code FROM corp_events r
           WHERE r.kind = 'record_date' AND r.date > ?
             AND NOT EXISTS (SELECT 1 FROM corp_events d
                             WHERE d.code = r.code AND d.kind IN ('cash_dividend', 'stock_dividend')
                               AND d.announced <= r.date AND d.announced >= date(r.date, ?))
           ORDER BY r.date, r.code"""
    with sqlite3.connect(db_path) as con:       # read-only use; a WAL store needs its -shm file, so not mode=ro
        return [c for (c,) in con.execute(q, (after, f"-{DECLARATION_DAYS_BACK} day"))]


def fill_declarations(db_path: str, codes: list[str], get=None, delay: float = ARCHIVE_DELAY_S) -> dict:
    """Read each company's DSE news archive (AmarStock's copy) and store its events, as the engine's own
    news-history job does for every company. Returns {read, failed, added}."""
    from dse_pnf import db, events

    get = get or events.http_get
    read, failed, added = [], [], 0
    for k, code in enumerate(codes[:MAX_ARCHIVES]):
        if k and delay:
            time.sleep(delay)
        try:
            evs = events.events(events.news_archive(code, get))
        except Exception:      # one company's archive failing must not stop the others
            failed.append(code)
            continue
        with sqlite3.connect(db_path) as con:
            added += db.upsert_events(con, evs)
        read.append(code)
    return {"read": read, "failed": failed, "added": added}


def refresh(db_path: str, today: date | None = None) -> dict:
    """Backfill first when the store is older than one refresh can fill, then refresh. Returns
    {ok, detail, before, after}; ok is False when the engine's job failed."""
    from pnf_app import jobs as engine_jobs
    from pnf_app.server import App

    before = last_session(db_path)
    app = App(db_path, scheduler=False)
    today = today or date.today()
    steps = []
    if before and date.fromisoformat(before) < today - timedelta(days=engine_jobs.MAX_GAP_DAYS):
        start = (date.fromisoformat(before) + timedelta(days=1)).isoformat()
        steps.append(_run(app, "backfill", start=start))
    steps.append(_run(app, "refresh"))
    after = last_session(db_path)
    detail = "; ".join(str(s.get("detail")) for s in steps)
    missing = missing_declarations(db_path, after or before or "")
    if missing:
        f = fill_declarations(db_path, missing)
        detail += (f"; dividend declarations: news history of {len(f['read'])} companies with a record date ahead "
                   f"({f['added']} events)" + (f", {len(f['failed'])} failed" if f["failed"] else ""))
    return {"ok": all(s.get("ok") for s in steps), "detail": detail, "before": before, "after": after}
