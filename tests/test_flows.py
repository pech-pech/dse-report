from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from dsereport import flows

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"

# 2026-11-12 Thu, 15 Sun, 16 Mon, 17 Tue
SESSIONS = ["2026-10-29", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]


def _inputs():
    daily = [
        # code, date, close, prev_close, volume
        ["AAA", "2026-10-29", 10.0, 10.0, 1_000_000],   # flat 1 crore
        ["AAA", "2026-11-12", 10.0, 9.0, 1_000_000],    # in 1 crore
        ["BBB", "2026-11-12", 20.0, 21.0, 500_000],     # out 1 crore
        ["AAA", "2026-11-15", 11.0, 10.0, 2_000_000],   # in 2.2
        ["BBB", "2026-11-15", 20.0, 20.0, 1_000_000],   # flat 2
        ["AAA", "2026-11-16", 10.0, 11.0, 1_000_000],   # out 1
        ["CCC", "2026-11-16", 5.0, 4.0, 2_000_000],     # in 1 (no sector)
        ["AAA", "2026-11-17", 12.0, 10.0, 5_000_000],   # in 6
        ["BBB", "2026-11-17", 18.0, 20.0, 1_000_000],   # out 1.8
        ["BBB", "2026-11-17", None, 20.0, 1_000_000],   # broken row: skipped
    ]
    return {
        "asof": "2026-11-17",
        "sessions": SESSIONS,
        "daily": daily,
        "stocks": {"AAA": {"sector": "Bank"}, "BBB": {"sector": "Cement"}},
    }


def test_session_rows_counts_and_crore():
    rows = flows.session_rows(_inputs())
    assert [r["date"] for r in rows] == SESSIONS
    last = rows[-1]
    assert (last["adv"], last["dec"], last["unch"]) == (1, 1, 0)
    assert last["turnover_cr"] == pytest.approx(7.8)
    assert last["in_cr"] == pytest.approx(6.0)
    assert last["out_cr"] == pytest.approx(1.8)
    assert last["flat_cr"] == 0
    assert last["net_cr"] == pytest.approx(4.2)
    assert rows[2]["unch"] == 1 and rows[2]["flat_cr"] == pytest.approx(2.0)


def test_session_rows_keeps_only_the_last_row_sessions():
    I = _inputs()
    I["daily"] = [["AAA", f"2026-{m:02d}-{d:02d}", 1.0, 1.0, 1] for m in (8, 9, 10) for d in range(1, 21)]
    rows = flows.session_rows(I)
    assert len(rows) == flows.ROW_SESSIONS == 45
    assert rows[-1]["date"] == "2026-10-20"


def test_session_rows_does_not_mutate_inputs():
    I = _inputs()
    before = copy.deepcopy(I)
    flows.session_rows(I)
    flows.period_flow(I, "week")
    assert I == before


def test_period_flow_day():
    f = flows.period_flow(_inputs(), "day")
    assert f["sessions"] == 1
    assert f["turnover_cr"] == pytest.approx(7.8)
    assert f["turnover_avg_cr"] == pytest.approx(7.8)
    # the 4 sessions before: 1, 2, 4.2, 2 -> avg 2.3
    assert f["vs_avg20"] == pytest.approx(round(7.8 / 2.3, 2))
    assert f["net_cr"] == pytest.approx(4.2)
    assert f["by_sector"] == {"Bank": pytest.approx(6.0), "Cement": pytest.approx(-1.8)}


def test_period_flow_week_sums_sessions_and_sectors():
    f = flows.period_flow(_inputs(), "week")   # 15, 16, 17 Nov
    assert f["sessions"] == 3
    assert (f["adv"], f["dec"], f["unch"]) == (3, 2, 1)
    assert f["turnover_cr"] == pytest.approx(4.2 + 2.0 + 7.8)
    assert f["turnover_avg_cr"] == pytest.approx(14.0 / 3, abs=0.01)
    assert f["in_cr"] == pytest.approx(9.2)
    assert f["out_cr"] == pytest.approx(2.8)
    assert f["flat_cr"] == pytest.approx(2.0)
    assert f["net_cr"] == pytest.approx(6.4)
    assert f["vs_avg20"] == pytest.approx(round((14.0 / 3) / 1.5, 2))
    assert f["by_sector"]["Bank"] == pytest.approx(7.2)
    assert f["by_sector"]["Other"] == pytest.approx(1.0)
    assert f["last14"] == pytest.approx([0.0, 0.0, 2.2, 0.0, 4.2])
    assert f["inflow_sessions_14"] == 2


def test_period_flow_without_earlier_sessions_has_no_ratio():
    I = _inputs()
    I["sessions"] = ["2026-11-15", "2026-11-16", "2026-11-17"]
    I["daily"] = [r for r in I["daily"] if r[1] >= "2026-11-15"]
    assert flows.period_flow(I, "week")["vs_avg20"] is None


def test_period_flow_empty_inputs():
    f = flows.period_flow({"sessions": [], "daily": [], "stocks": {}}, "day")
    assert f["sessions"] == 0 and f["turnover_avg_cr"] is None and f["last14"] == []


def test_bad_period_raises():
    with pytest.raises(ValueError):
        flows.period_flow(_inputs(), "year")


@pytest.fixture(scope="module")
def real():
    return json.loads(FIXTURE.read_text())


def test_real_fixture_shape_and_sanity(real):
    rows = flows.session_rows(real)
    assert len(rows) == flows.ROW_SESSIONS
    last = rows[-1]
    assert last["date"] == "2026-11-17"
    assert 700 < last["turnover_cr"] < 1000           # about Tk 840 crore
    assert last["adv"] + last["dec"] + last["unch"] > 300
    for p in ("day", "week", "month"):
        f = flows.period_flow(real, p)
        json.dumps(f, allow_nan=False)
        assert f["sessions"] >= 1
        assert len(f["last14"]) == 14
        assert f["in_cr"] + f["out_cr"] + f["flat_cr"] == pytest.approx(f["turnover_cr"], abs=0.5)
        assert f["vs_avg20"] is not None and 0.2 < f["vs_avg20"] < 5
        assert sum(f["by_sector"].values()) == pytest.approx(f["net_cr"], abs=0.5)
        assert all(not math.isnan(v) for v in f["by_sector"].values())
