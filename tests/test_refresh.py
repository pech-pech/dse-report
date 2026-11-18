"""The refresh wrapper around the engine's job runner, with a fake App (no network)."""
import sqlite3
from datetime import date

import pytest

from dsereport import cli, refresh


def _store(path, last):
    from dse_pnf import db as engine_db
    engine_db.connect(str(path)).close()                    # the engine's own schema (prices, corp_events, ...)
    with sqlite3.connect(path) as con:
        con.execute("INSERT INTO prices (ticker, date, open, high, low, close, volume, source) "
                    "VALUES ('00DSEX', ?, 5000, 5000, 5000, 5000, 0, 'test')", (last,))
    return str(path)


class FakeJobs:
    def __init__(self, results, path, add=None):
        self.results, self.path, self.add, self.started, self._st = results, path, add, [], {}

    def start(self, kind, **kw):
        self.started.append((kind, kw))
        ok, detail = self.results[kind]
        if ok and self.add:
            with sqlite3.connect(self.path) as con:
                con.execute("INSERT INTO prices (ticker, date, open, high, low, close, volume, source) "
                            "VALUES ('00DSEX', ?, 5010, 5010, 5010, 5010, 0, 'test')", (self.add,))
        self._st = {"running": False, "last": {"kind": kind, "ok": ok, "detail": detail}}
        return True

    def wait(self, timeout=None):
        pass

    def status(self):
        return self._st

    def cancel(self):
        pass


@pytest.fixture
def fake_app(monkeypatch):
    made = {}

    def install(results, add=None):
        import pnf_app.server as server

        class App:
            def __init__(self, path, scheduler=False):
                self.jobs = FakeJobs(results, path, add)
                made["app"] = self
        monkeypatch.setattr(server, "App", App)
        return made
    return install


def test_refresh_runs_the_engine_job_and_reports_sessions(tmp_path, fake_app):
    db = _store(tmp_path / "p.sqlite3", "2026-11-16")
    made = fake_app({"refresh": (True, "1 day saved")}, add="2026-11-17")
    r = refresh.refresh(db, today=date(2026, 11, 18))
    assert r == {"ok": True, "detail": "1 day saved", "before": "2026-11-16", "after": "2026-11-17"}
    assert [k for k, _ in made["app"].jobs.started] == ["refresh"]


def test_old_store_is_backfilled_before_the_refresh(tmp_path, fake_app):
    db = _store(tmp_path / "p.sqlite3", "2026-09-01")
    made = fake_app({"backfill": (True, "40 days"), "refresh": (True, "up to date")})
    r = refresh.refresh(db, today=date(2026, 11, 18))
    assert made["app"].jobs.started == [("backfill", {"start": "2026-09-02"}), ("refresh", {})]
    assert r["ok"] and r["detail"] == "40 days; up to date"


def test_failed_job_fails_the_command(tmp_path, fake_app, capsys):
    db = _store(tmp_path / "p.sqlite3", "2026-11-16")
    fake_app({"refresh": (False, "failed: AmarStock down")})
    assert cli.main(["refresh", "--db", db]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_busy_runner_raises(tmp_path, monkeypatch):
    db = _store(tmp_path / "p.sqlite3", "2026-11-16")

    class Busy:
        def start(self, kind, **kw):
            return False

        def status(self):
            return {"kind": "backfill"}

    class App:
        jobs = Busy()
    with pytest.raises(RuntimeError, match="already running"):
        refresh._run(App(), "refresh")


def test_timeout_cancels_the_job():
    class Slow:
        cancelled = False

        def start(self, kind, **kw):
            return True

        def wait(self, timeout=None):
            pass

        def status(self):
            return {"running": True}

        def cancel(self):
            Slow.cancelled = True

    class App:
        jobs = Slow()
    with pytest.raises(TimeoutError):
        refresh._run(App(), "refresh")
    assert Slow.cancelled


def _event(db, code, kind, day, announced, value=None, detail=""):
    from dse_pnf import db as engine_db
    with sqlite3.connect(db) as con:
        engine_db.upsert_events(con, [{"code": code, "kind": kind, "date": day, "announced": announced,
                                       "value": value, "detail": detail, "title": "t", "source": "test",
                                       "vkey": ""}])


def test_missing_declarations_lists_record_dates_without_a_dividend(tmp_path):
    db = _store(tmp_path / "p.sqlite3", "2026-11-17")
    _event(db, "HASDIV", "cash_dividend", "2026-10-27", "2026-10-27", 40.0, "40% cash")
    _event(db, "HASDIV", "record_date", "2026-11-24", "2026-11-15", detail="record date")
    _event(db, "NODIV", "record_date", "2026-11-24", "2026-11-15", detail="record date")
    _event(db, "PAST", "record_date", "2026-11-10", "2026-11-01", detail="record date")
    assert refresh.missing_declarations(db, "2026-11-17") == ["NODIV"]


def test_fill_declarations_stores_archive_events_and_survives_failures(tmp_path, monkeypatch):
    from dse_pnf import events as engine_events
    db = _store(tmp_path / "p.sqlite3", "2026-11-17")
    calls = []

    def archive(code, get):
        calls.append(code)
        if code == "BAD":
            raise OSError("down")
        return ["item"]
    monkeypatch.setattr(engine_events, "news_archive", archive)
    monkeypatch.setattr(engine_events, "events", lambda items: [
        {"code": calls[-1], "kind": "cash_dividend", "date": "2026-10-27", "announced": "2026-10-27",
         "value": 40.0, "detail": "40% cash", "title": "Dividend Declaration", "source": "test", "vkey": ""}])
    out = refresh.fill_declarations(db, ["OK", "BAD"], get=object(), delay=0)
    assert out["read"] == ["OK"] and out["failed"] == ["BAD"] and out["added"] == 1
    assert refresh.missing_declarations(db, "2026-11-17") == []


def test_refresh_fills_declarations_for_record_dates_ahead(tmp_path, fake_app, monkeypatch):
    db = _store(tmp_path / "p.sqlite3", "2026-11-16")
    _event(db, "NODIV", "record_date", "2026-11-24", "2026-11-15", detail="record date")
    fake_app({"refresh": (True, "1 day saved")}, add="2026-11-17")
    seen = {}
    monkeypatch.setattr(refresh, "fill_declarations",
                        lambda path, codes: seen.setdefault("codes", codes) and {"read": codes, "failed": [], "added": 2})
    r = refresh.refresh(db, today=date(2026, 11, 18))
    assert seen["codes"] == ["NODIV"]
    assert "news history of 1 companies with a record date ahead (2 events)" in r["detail"]
