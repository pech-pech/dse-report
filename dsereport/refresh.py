"""Bring a price store up to date through the engine's own refresh job (prices, bonus adjustments, sectors,
company news and corporate events), the same job the desktop app runs. Used by the daily cloud build.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

DSEX = "00DSEX"
JOB_TIMEOUT_S = 30 * 60


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
    return {"ok": all(s.get("ok") for s in steps), "detail": "; ".join(str(s.get("detail")) for s in steps),
            "before": before, "after": last_session(db_path)}
