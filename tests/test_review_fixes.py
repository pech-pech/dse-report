"""Fixes from the 2026-11-18 code review."""
from dsereport import brief, setups


def test_sector_without_a_change_is_never_called_the_laggard():
    rows = [{"sector": "Bank", "chg_pct": 2.0, "bp": 50.0, "bp_column": "X"},
            {"sector": "Jute", "chg_pct": -1.0}, {"sector": "SME Sector", "chg_pct": None}]
    assert "Jute lagged" in brief._leaders_sentence(rows, None, "today")
    assert "weakest Jute" in brief._a_leader(rows, "today")["detail"]
    assert brief._a_leader([{"sector": "X", "chg_pct": None}], "today")["state"] != "X"


def test_glance_says_advances_and_declines_for_several_sessions():
    flow = {"adv": 2278, "dec": 2228, "unch": 601, "sessions": 13}
    assert brief._glance(None, flow)[1][0] == "Advances / declines"
    assert brief._glance(None, {**flow, "sessions": 1})[1][0] == "Up / down"


def test_no_ema200_means_no_ema200_caution():
    s = {"sector": "Bank", "close": [10.0], "ema200": None}
    assert setups._caution(s, "X") is None
    assert "below its EMA200" in setups._caution({**s, "ema200": 12.0}, "X")


def test_mfi_with_a_missing_bar_does_not_stop_the_build():
    s = {"high": [1.0, None], "low": [1.0, 1.0], "close": [1.0, 1.0], "volume": [1, 1]}
    assert setups._mfi_pair(s) == (None, None)
