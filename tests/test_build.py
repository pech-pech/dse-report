"""Integration: the whole report from the real 17 Nov 2026 inputs, validated as the app will receive it."""
import json
import os

import pytest

from dsereport import build, cli, schema

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "inputs_2026-11-17.json")
FEED = {"fetched_at": "2026-11-17T11:00:00Z", "failed": ["TBS · Economy"], "items": [
    {"source": "The Daily Star", "section": "Stock", "title": "Stocks edge up as banks recover", "link": "https://example.test/a",
     "published": "2026-11-17", "tags": []}]}


@pytest.fixture(scope="module")
def inputs():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def report(inputs):
    return build.build_report(inputs, FEED, built_at="2026-11-17T11:05:00Z")


def test_report_validates(report):
    assert schema.validate(report) == []


def test_report_is_dated_and_complete(report):
    assert report["asOf"] == "2026-11-17" and report["builtAt"] == "2026-11-17T11:05:00Z"
    assert set(report["periods"]) == {"day", "week", "month"}
    assert report["papersFailed"] == ["TBS · Economy"]
    assert report["notification"]["title"]


def test_setups_are_numbered_from_card_six(report):
    assert [s["card"] for s in report["setups"]] == list(range(6, 6 + len(report["setups"])))
    assert len(report["setups"]) <= build.SETUPS_SHOWN


def test_periods_differ_where_they_should(report):
    d, m = report["periods"]["day"], report["periods"]["month"]
    assert d["sessions"] == 1 and m["sessions"] > 1
    assert d["market"]["dsex"]["chg_pct"] != m["market"]["dsex"]["chg_pct"]


def test_inputs_are_not_changed(inputs):
    before = json.dumps(inputs, sort_keys=True, default=str)
    build.build_report(inputs, None, built_at="x")
    assert json.dumps(inputs, sort_keys=True, default=str) == before


def test_report_is_small_enough_for_a_phone(report):
    assert len(json.dumps(report, separators=(",", ":"))) < 400_000


def test_cli_writes_latest_dated_and_index(tmp_path, capsys):
    out = tmp_path / "site"
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(out), "--no-papers"]) == 0
    v1 = out / "v1"
    assert (v1 / "latest.json").exists() and (v1 / "2026-11-17.json").exists()
    assert json.loads((v1 / "index.json").read_text()) == ["2026-11-17"]
    assert json.loads((v1 / "latest.json").read_text())["schema"] == 1
    assert "Wrote" in capsys.readouterr().out


def test_cli_refuses_an_invalid_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(schema, "validate", lambda r: ["report: missing setups"])
    monkeypatch.setattr(cli.schema, "validate", lambda r: ["report: missing setups"])
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(tmp_path), "--no-papers"]) == 1
    assert not (tmp_path / "v1" / "latest.json").exists()
    assert "failed validation" in capsys.readouterr().err


def test_cli_inputs_command(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_inputs", lambda args: {"asof": "2026-11-17"})
    out = tmp_path / "in.json"
    assert cli.main(["inputs", "--db", "x", "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == {"asof": "2026-11-17"}


def test_copy_store_makes_a_readable_copy(tmp_path):
    import sqlite3
    src = tmp_path / "src.sqlite3"
    with sqlite3.connect(src) as c:
        c.execute("create table prices (ticker text)")
        c.execute("insert into prices values ('GP')")
    dst = cli._copy_store(str(src), str(tmp_path))
    with sqlite3.connect(dst) as c:
        assert c.execute("select ticker from prices").fetchone() == ("GP",)


def test_cli_if_newer_skips_a_session_the_site_already_has(tmp_path, capsys):
    out = tmp_path / "site"
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(out), "--no-papers"]) == 0
    before = (out / "v1" / "latest.json").read_text()
    capsys.readouterr()
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(out), "--no-papers", "--if-newer"]) == 0
    assert "No new session" in capsys.readouterr().out
    assert (out / "v1" / "latest.json").read_text() == before


def test_cli_if_newer_writes_when_the_site_is_older(tmp_path):
    v1 = tmp_path / "site" / "v1"
    v1.mkdir(parents=True)
    (v1 / "latest.json").write_text(json.dumps({"asOf": "2026-11-16"}))
    (v1 / "index.json").write_text(json.dumps(["2026-11-16"]))
    (v1 / "2026-11-16.json").write_text("{}")
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(tmp_path / "site"), "--no-papers", "--if-newer"]) == 0
    assert json.loads((v1 / "latest.json").read_text())["asOf"] == "2026-11-17"
    assert json.loads((v1 / "index.json").read_text()) == ["2026-11-17", "2026-11-16"]


def test_cli_prunes_reports_that_leave_the_index(tmp_path, monkeypatch):
    v1 = tmp_path / "site" / "v1"
    v1.mkdir(parents=True)
    old = [f"2026-08-{d:02d}" for d in range(1, 31)] + [f"2026-09-{d:02d}" for d in range(1, 31)]
    for d in old:
        (v1 / f"{d}.json").write_text("{}")
    (v1 / "index.json").write_text(json.dumps(old))
    assert cli.main(["build", "--inputs", FIXTURE, "--out", str(tmp_path / "site"), "--no-papers"]) == 0
    index = json.loads((v1 / "index.json").read_text())
    assert len(index) == cli.KEEP_REPORTS and index[0] == "2026-11-17" and "2026-08-01" not in index
    assert not (v1 / "2026-08-01.json").exists() and (v1 / "2026-08-02.json").exists()
    assert (v1 / "latest.json").exists() and (v1 / "index.json").exists()
