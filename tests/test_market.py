from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dsereport.market import market_block

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"
SESSIONS = ["2026-10-29", "2026-11-01", "2026-11-02", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]


def _inputs(column="X", bp_column="X"):
    return {
        "asof": "2026-11-17",
        "sessions": SESSIONS,
        "dsex": {
            "dates": SESSIONS,
            "close": [5300.0, 5400.0, 5410.0, 5420.0, 5460.0, 5463.0, 5496.7],
            "pf": {"cols": [["O", 5440.0, 5464.0, 3], [column, 5456.0, 5496.0, 6]], "reversal": 3},
            "last_signal": {"kind": "BUY", "pattern": "Bullish Signal (Diagonal Triple Top)", "date": "2026-11-17"},
            "status": "BUY",
            "objective": {"target": 5600.0},
            "action_points": {"column": column, "next": 5504.0 if column == "X" else 5440.0,
                              "reverse": 5472.0 if column == "X" else 5520.0},
            "stops": {"stop": 5440.0, "risk_pct": 1.03},
        },
        "market_bp": {"signal": "SELL", "column": bp_column, "column_since": "2026-11-16", "reading": 34.0,
                      "reverse_at": 28.0 if bp_column == "X" else 40.0, "bp": 34.0, "zone": "below 50 midline"},
        "bp_series": [[s, v] for s, v in zip(SESSIONS, [30.0, 31.0, 29.5, 33.0, 31.6, 32.3, 34.0])],
        "regime": {"key": "pullback", "name": "Pullback", "note": "DSEX above its EMA200 but its EMA50 falling",
                   "record": {"10": {}}},
    }


def test_day_change_vs_previous_session():
    m = market_block(_inputs(), "day")
    assert m["asof"] == "2026-11-17"
    assert m["label"] == "Tue 17 Nov"
    assert m["dsex"] == {"close": 5496.7, "chg_pts": 33.7, "chg_pct": 0.62}


def test_week_and_month_use_base_session():
    week = market_block(_inputs(), "week")
    assert week["dsex"]["chg_pts"] == pytest.approx(76.7)       # vs 12 Nov (Thu before Sunday 15 Nov)
    assert week["bp"]["start_value"] == 33.0
    month = market_block(_inputs(), "month")
    assert month["dsex"]["chg_pts"] == pytest.approx(196.7)     # vs 29 Oct
    assert month["bp"]["start_value"] == 30.0
    assert month["label"] == "1–17 Nov"


def test_pf_block():
    pf = market_block(_inputs(), "day")["pf"]
    assert pf == {"status": "BUY", "column": "X", "pattern": "Bullish Signal (Diagonal Triple Top)",
                  "signal_date": "2026-11-17", "target": 5600.0, "next_box": 5504.0, "reverse_at": 5472.0,
                  "stop": 5440.0, "trend": None, "trend_level": None}


def test_bp_block_and_path():
    bp = market_block(_inputs(), "day")["bp"]
    assert bp["value"] == 34.0 and bp["column"] == "X" and bp["signal"] == "SELL"
    assert bp["zone"] == "below 50 midline" and bp["column_since"] == "2026-11-16" and bp["reverse_at"] == 28.0
    assert bp["start_value"] == 32.3
    assert bp["path"] == [30.0, 31.0, 29.5, 33.0, 31.6, 32.3, 34.0]


def test_regime_has_only_name_and_note():
    assert market_block(_inputs(), "day")["regime"] == {
        "name": "Pullback", "note": "DSEX above its EMA200 but its EMA50 falling"}


def test_levels_rising_columns():
    levels = market_block(_inputs(), "day")["levels"]
    assert 3 <= len(levels) <= 4
    text = " ".join(x["text"] for x in levels)
    assert "rising X column" in text and "5,504" in text and "5,472" in text
    assert "34.0%" in text and "below the 50 midline" in text and "28.0%" in text
    assert "5,440" in text and "1.0% below" in text
    assert "BUY: a Diagonal Triple Top on Tue 17 Nov, with a price objective of 5,600." in text
    assert all(set(x) == {"label", "text"} and x["text"].endswith(".") for x in levels)


def test_levels_falling_columns():
    I = _inputs(column="O", bp_column="O")
    I["market_bp"]["bp"] = I["market_bp"]["reading"] = 62.0
    text = " ".join(x["text"] for x in market_block(I, "day")["levels"])
    assert "falling O column" in text and "down to 5,440" in text and "5,520 would turn it to an X column" in text
    assert "62.0%" in text and "above the 50 midline" in text and "rise to 40.0%" in text


def test_stop_above_close_is_said_plainly():
    I = _inputs()
    I["dsex"]["stops"] = {"stop": 5550.0}
    I["dsex"]["last_signal"] = {"pattern": "Double Top"}
    text = " ".join(x["text"] for x in market_block(I, "day")["levels"])
    assert "above the close" in text
    assert "BUY: a Double Top, with" in text


def test_missing_pieces_give_none_not_errors():
    I = _inputs()
    I["dsex"]["stops"] = {}
    I["dsex"]["objective"] = None
    I["market_bp"] = {}
    I["bp_series"] = []
    I["sessions"] = ["2026-11-17"]
    I["dsex"]["dates"], I["dsex"]["close"] = ["2026-11-17"], [5496.7]
    m = market_block(I, "day")
    assert m["dsex"]["chg_pts"] is None and m["dsex"]["chg_pct"] is None
    assert m["pf"]["target"] is None and m["pf"]["stop"] is None
    assert m["bp"]["value"] is None and m["bp"]["path"] == [] and m["bp"]["start_value"] is None
    assert len(m["levels"]) >= 1
    json.dumps(m, allow_nan=False)


def test_column_falls_back_to_last_pf_column():
    I = _inputs(column="O")
    I["dsex"]["action_points"] = {"next": 5440.0, "reverse": 5520.0}
    assert market_block(I, "day")["pf"]["column"] == "O"


def test_does_not_mutate_inputs():
    I = _inputs()
    before = copy.deepcopy(I)
    market_block(I, "week")
    assert I == before


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        market_block(_inputs(), "year")


def test_real_fixture():
    I = json.loads(FIXTURE.read_text())
    for p in ("day", "week", "month"):
        m = market_block(I, p)
        json.dumps(m, allow_nan=False)
        assert m["dsex"]["close"] == pytest.approx(5496.73, abs=0.01)
        assert m["pf"]["status"] == "BUY" and m["pf"]["target"] == 5600.0
        assert m["pf"]["next_box"] == 5504.0 and m["pf"]["reverse_at"] == 5472.0
        assert m["bp"]["value"] == 34.0 and m["bp"]["column"] == "X" and len(m["bp"]["path"]) == 30
        assert 3 <= len(m["levels"]) <= 4
    day = market_block(I, "day")
    assert day["dsex"]["chg_pts"] == pytest.approx(33.44, abs=0.01)
    assert day["bp"]["start_value"] == 32.3
