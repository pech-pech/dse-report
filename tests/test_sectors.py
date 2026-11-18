from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from dsereport import sectors

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"

# Mon 2 Nov .. Tue 17 Nov 2026 style sessions (Sun-Thu); last is Tue 17 Nov.
SESSIONS = ["2026-10-29", "2026-11-01", "2026-11-02", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]


def _series(closes):
    return {"dates": list(SESSIONS), "close": list(closes)}


def _row(sector, **kw):
    base = {"sector": sector, "stocks": 2, "score": 50, "bp": 50.0, "bp_column": "X", "bp_zone": "above 50 midline",
            "bp_signal": "BUY", "rs_signal": "BUY", "rs_column": "X"}
    base.update(kw)
    return base


def _inputs():
    return {
        "asof": "2026-11-17",
        "sessions": list(SESSIONS),
        "sector_rows": [
            _row("Bank", bp=41.7, bp_column="O", bp_zone="below 50 midline", bp_signal="SELL", rs_signal="SELL",
                 rs_column="O", stocks=2, score=30),
            _row("Pharma", bp=62.5, stocks=2, score=80),
        ],
        "sector_series": {
            "Bank": {**_series([100, 100, 100, 100, 100, 95, 90]), "members": ["B1", "B2"]},
            "Pharma": {**_series([100, 100, 100, 100, 100, 104, 110]), "members": ["P1", "P2", "P3"]},
        },
        "stocks": {
            "B1": {"close": [10, 9], "ema50": [9.5, 9.5]},
            "B2": {"close": [10, 11], "ema50": [10, 10]},
            "P1": {"close": [5, 6], "ema50": [5, 5]},
            "P2": {"close": [5, 6], "ema50": [5, None]},
        },
    }


def test_chg_pct_vs_base_session_for_each_period():
    I = _inputs()
    day = {r["sector"]: r["chg_pct"] for r in sectors.sector_table(I, "day", {})}
    week = {r["sector"]: r["chg_pct"] for r in sectors.sector_table(I, "week", {})}
    month = {r["sector"]: r["chg_pct"] for r in sectors.sector_table(I, "month", {})}
    assert day == {"Bank": pytest.approx(-5.26, abs=0.01), "Pharma": pytest.approx(5.77, abs=0.01)}
    assert week == {"Bank": -10.0, "Pharma": 10.0}       # base Thu 12 Nov
    assert month == {"Bank": -10.0, "Pharma": 10.0}      # base Thu 29 Oct


def test_rows_sorted_by_change_and_carry_bp_rs_and_flow():
    rows = sectors.sector_table(_inputs(), "week", {"Pharma": 12.345, "Bank": -3.2})
    assert [r["sector"] for r in rows] == ["Pharma", "Bank"]
    bank = rows[1]
    assert bank["bp"] == 41.7 and bank["bp_column"] == "O" and bank["bp_zone"] == "below 50 midline"
    assert bank["bp_signal"] == "SELL" and bank["rs_signal"] == "SELL" and bank["rs_column"] == "O"
    assert rows[0]["net_cr"] == 12.35 and bank["net_cr"] == -3.2
    assert bank["stocks"] == 2 and bank["score"] == 30


def test_missing_flow_is_zero():
    rows = sectors.sector_table(_inputs(), "day", {"Pharma": 1.0})
    assert {r["sector"]: r["net_cr"] for r in rows} == {"Pharma": 1.0, "Bank": 0.0}


def test_above_ema50_counts_members_with_data():
    rows = {r["sector"]: r for r in sectors.sector_table(_inputs(), "day", {})}
    assert rows["Bank"]["above_ema50_pct"] == 50.0      # B1 below, B2 above
    assert rows["Pharma"]["above_ema50_pct"] == 100.0   # P1 above; P2 no ema50; P3 missing


def test_above_ema50_none_without_data():
    I = _inputs()
    I["stocks"] = {}
    rows = sectors.sector_table(I, "day", {})
    assert all(r["above_ema50_pct"] is None for r in rows)


def test_macd_state_needs_enough_closes():
    rows = sectors.sector_table(_inputs(), "day", {})
    assert all(r["macd_state"] is None for r in rows)    # 7 closes is too few


def test_macd_state_above_and_below_signal():
    up = [100 + i * 0.1 for i in range(60)] + [106 + i * 2 for i in range(10)]
    down = [100 - i * 0.1 for i in range(60)] + [94 - i * 2 for i in range(10)]
    assert sectors.macd_state(up) == "above signal"
    assert sectors.macd_state(down) == "below signal"


def test_change_none_when_base_missing_sorts_last():
    I = _inputs()
    I["sector_series"]["Bank"] = {"dates": ["2026-11-17"], "close": [90], "members": []}
    rows = sectors.sector_table(I, "week", {})
    assert rows[-1]["sector"] == "Bank" and rows[-1]["chg_pct"] is None


def test_inputs_not_mutated():
    I = _inputs()
    before = copy.deepcopy(I)
    sectors.sector_table(I, "week", {"Bank": 1.0})
    assert I == before


def _hrow(sector, chg, **kw):
    base = {"sector": sector, "chg_pct": chg, "bp": 55.0, "bp_column": "X", "bp_zone": "above 50 midline",
            "bp_signal": "BUY", "rs_signal": "BUY", "rs_column": "X", "net_cr": 10.0, "above_ema50_pct": 60.0,
            "macd_state": "above signal", "stocks": 20, "score": 70}
    base.update(kw)
    return base


def test_highlights_picks_strongest_second_weakest():
    rows = [
        _hrow("Pharma", 4.2, net_cr=25.4),
        _hrow("Textile", 2.1, rs_signal="SELL", net_cr=3.0),
        _hrow("Food", 0.5),
        _hrow("Bank", -3.4, bp=22.0, bp_column="O", bp_zone="oversold (<30)", bp_signal="SELL", net_cr=-18.6,
              above_ema50_pct=12.5, macd_state="below signal", rs_signal="SELL", rs_column="O"),
    ]
    hl = sectors.highlights(rows)
    assert [h["sector"] for h in hl] == ["Pharma", "Textile", "Bank"]
    assert [h["tone"] for h in hl] == ["up", "up", "down"]
    assert hl[0]["chg_pct"] == 4.2
    for h in hl:
        assert 3 <= len(h["reasons"]) <= 4
        assert all(any(ch.isdigit() for ch in r) or "signal" in r for r in h["reasons"])
    strong = " ".join(hl[0]["reasons"])
    assert "+4.2%" in strong and "Tk 25.4 crore" in strong and "55.0%" in strong
    weak = " ".join(hl[2]["reasons"])
    assert "−3.4%" in weak and "oversold" in weak and "Tk 18.6 crore" in weak and "22.0%" in weak


def test_highlights_rising_bp_and_rs_buy_mentioned():
    hl = sectors.highlights([_hrow("A", 3.0), _hrow("B", 1.0), _hrow("C", -1.0)])
    text = " ".join(hl[0]["reasons"])
    assert "rising" in text and "relative strength" in text.lower()


def test_highlights_short_inputs():
    assert sectors.highlights([]) == []
    one = sectors.highlights([_hrow("A", 1.0)])
    assert [h["sector"] for h in one] == ["A"]
    two = sectors.highlights([_hrow("A", 1.0), _hrow("B", -1.0)])
    assert [h["sector"] for h in two] == ["A", "B"]


def test_highlights_skip_rows_without_change():
    hl = sectors.highlights([_hrow("A", 2.0), _hrow("B", 1.0), _hrow("C", -1.0), _hrow("D", None)])
    assert [h["sector"] for h in hl] == ["A", "B", "C"]


def test_highlights_handles_missing_numbers():
    row = _hrow("A", 0.0, above_ema50_pct=None, macd_state=None, net_cr=0.0, bp=None)
    hl = sectors.highlights([row])
    assert hl[0]["tone"] == "flat" and 3 <= len(hl[0]["reasons"]) <= 4


@pytest.fixture(scope="module")
def real():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_real_fixture_shape(real, period):
    flow = {"Bank": 12.5, "Pharmaceuticals": -4.0}
    rows = sectors.sector_table(real, period, flow)
    assert len(rows) == 20
    keys = {"sector", "chg_pct", "bp", "bp_column", "bp_zone", "bp_signal", "rs_signal", "rs_column", "net_cr",
            "above_ema50_pct", "macd_state", "stocks", "score"}
    changes = [r["chg_pct"] for r in rows]
    assert all(c is not None and math.isfinite(c) and abs(c) < 50 for c in changes)
    assert changes == sorted(changes, reverse=True)
    for r in rows:
        assert set(r) == keys
        assert r["macd_state"] in ("above signal", "below signal")
        assert r["above_ema50_pct"] is None or 0 <= r["above_ema50_pct"] <= 100
    assert next(r for r in rows if r["sector"] == "Bank")["net_cr"] == 12.5
    hl = sectors.highlights(rows)
    assert len(hl) == 3 and hl[0]["sector"] == rows[0]["sector"] and hl[2]["sector"] == rows[-1]["sector"]
    json.dumps({"rows": rows, "hl": hl}, allow_nan=False)
