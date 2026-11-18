"""The refresh wrapper around the engine's job runner, with a fake App (no network)."""
import sqlite3
from datetime import date

import pytest

from dsereport import cli, refresh


def _store(path, last):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        con.execute("INSERT INTO prices VALUES ('00DSEX', ?, 5000)", (last,))
    return str(path)


class FakeJobs:
    def __init__(self, results, path, add=None):
        self.results, self.path, self.add, self.started, self._st = results, path, add, [], {}

    def start(self, kind, **kw):
        self.started.append((kind, kw))
        ok, detail = self.results[kind]
        if ok and self.add:
            with sqlite3.connect(self.path) as con:
                con.execute("INSERT INTO prices VALUES ('00DSEX', ?, 5010)", (self.add,))
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
