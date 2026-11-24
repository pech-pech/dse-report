from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dsereport import signals as S

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"
SESSIONS = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]
N = 20


def _stock(code, close_last=110.0, **kw):
    dates = ["2026-10-%02d" % d for d in range(1, N - len(SESSIONS) + 1)] + SESSIONS
    close = [100.0] * (N - 1) + [close_last]
    s = {
        "code": code, "sector": "Bank", "dates": dates, "close": close,
        "high": [c + 1 for c in close], "low": [c - 1 for c in close],
        "volume": [1000.0] * N, "ema20": [100.0] * N, "ema50": [100.0] * N, "ema200": 90.0,
        "macd": [1.0] * N, "macd_signal": [0.5] * N, "rvol": [1.0] * N, "bandwidth": [0.1] + [0.2] * (N - 1),
        "signal": "BUY", "pattern": "Double Top Breakout", "signal_date": "2026-01-01",
        "target": 130.0, "stop": 95.0, "vol_ratio": 1.0, "rs_column": "O",
        "pf": {"cols": [["X", 100, 110, 4]], "reversal": 3},
    }
    s.update(kw)
    return s


def _inputs(stocks, dsex_last=101.0):
    dates = ["2026-11-0%d" % d for d in range(1, 10 - len(SESSIONS) + 1)] + SESSIONS
    close = [100.0] * (len(dates) - 1) + [dsex_last]
    return {"asof": SESSIONS[-1], "sessions": SESSIONS,
            "dsex": {"dates": dates, "close": close},
            "stocks": {s["code"]: s for s in stocks}}


# --- period change -------------------------------------------------------

def test_period_change_vs_base_session():
    s = _stock("A", close_last=110.0)
    assert S.period_change(s["dates"], s["close"], "2026-11-16") == 10.0


def test_period_change_none_when_base_missing_or_zero():
    assert S.period_change(["2026-11-17"], [5.0], "2026-11-16") is None
    assert S.period_change(["2026-11-16", "2026-11-17"], [0.0, 5.0], "2026-11-16") is None
    assert S.period_change(["2026-11-16"], [5.0], None) is None


# --- chips ---------------------------------------------------------------

def test_chips_bullish_stock():
    chips = S.chips(_stock("A"), mfi=64.2)
    texts = [c["text"] for c in chips]
    assert texts == ["MACD ↑ signal", "Above EMA50 & EMA200", "MFI 64"]
    assert chips[0]["tone"] == "up" and chips[1]["tone"] == "up" and chips[2]["tone"] == "flat"


def test_chips_bearish_and_extremes():
    s = _stock("A", close_last=80.0, macd=[0.0] * N, ema200=85.0)
    chips = S.chips(s, mfi=85.0)
    assert chips[0] == {"text": "MACD ↓ signal", "tone": "down"}
    assert chips[1] == {"text": "Below EMA50 & EMA200", "tone": "down"}
    assert chips[2] == {"text": "MFI 85", "tone": "warn"}
    assert S.chips(s, mfi=15.0)[2]["tone"] == "warn"


def test_chips_mixed_averages():
    above50 = S.chips(_stock("A", ema200=120.0), mfi=None)
    assert above50[1] == {"text": "Above EMA50, below EMA200", "tone": "warn"}
    below50 = S.chips(_stock("A", close_last=95.0, ema200=90.0), mfi=None)
    assert below50[1] == {"text": "Below EMA50, above EMA200", "tone": "warn"}
    assert all(not c["text"].startswith("MFI") for c in above50)


def test_squeeze_chip_when_bandwidth_near_low():
    bw = [None] * 5 + [0.3] * (N - 6) + [0.105]
    bw[10] = 0.1
    chips = S.chips(_stock("A", bandwidth=bw), mfi=50.0)
    assert {"text": "Squeeze", "tone": "warn"} in chips
    wide = S.chips(_stock("A", bandwidth=[0.1] + [0.3] * (N - 1)), mfi=50.0)
    assert all(c["text"] != "Squeeze" for c in wide)


def test_chips_missing_data_skip_quietly():
    s = _stock("A", macd=[None] * N, ema50=[None] * N, ema200=None, bandwidth=[None] * N)
    assert S.chips(s, mfi=None) == []


def test_mfi_missing_bars_is_none():
    s = _stock("A", signal_date="2026-11-17")
    del s["high"]
    assert S.signal_lists(_inputs([s]), "day")["buys"][0]["mfi"] is None


# --- lists ---------------------------------------------------------------

def test_buys_and_sells_inside_window_sorted_by_rvol():
    stocks = [
        _stock("A", signal_date="2026-11-17", vol_ratio=1.5),
        _stock("B", signal_date="2026-11-17", vol_ratio=3.0),
        _stock("C", signal_date="2026-11-12", vol_ratio=9.0),
        _stock("D", signal="SELL", signal_date="2026-11-16", vol_ratio=1.0),
    ]
    day = S.signal_lists(_inputs(stocks), "day")
    assert [x["code"] for x in day["buys"]] == ["B", "A"]
    assert day["sells"] == [] and day["counts"]["sells"] == 0
    week = S.signal_lists(_inputs(stocks), "week")
    assert [x["code"] for x in week["buys"]] == ["B", "A"]  # C on 12 Nov is the previous week
    assert [x["code"] for x in week["sells"]] == ["D"]


def test_lists_capped_at_five_but_counts_full():
    stocks = [_stock("S%d" % i, signal_date="2026-11-17", vol_ratio=float(i)) for i in range(8)]
    out = S.signal_lists(_inputs(stocks), "day")
    assert len(out["buys"]) == S.MAX_ITEMS == 5
    assert out["counts"]["buys"] == 8
    assert [x["code"] for x in out["buys"]] == ["S7", "S6", "S5", "S4", "S3"]


def test_item_shape_and_values():
    s = _stock("A", signal_date="2026-11-17", vol_ratio=2.345)
    item = S.signal_lists(_inputs([s]), "day")["buys"][0]
    assert set(item) == {"code", "sector", "close", "chg_pct", "pattern", "signal_date", "target",
                         "stop", "rvol", "mfi", "chips", "state", "pf_cols"}
    assert item["chg_pct"] == 10.0 and item["close"] == 110.0 and item["rvol"] == 2.35
    assert item["pf_cols"] == [["X", 100, 110, 4]]
    assert item["target"] == 130.0 and item["stop"] == 95.0
    assert 0 <= item["mfi"] <= 100


def test_zero_target_becomes_none():
    s = _stock("A", signal_date="2026-11-17", target=0.0)
    assert S.signal_lists(_inputs([s]), "day")["buys"][0]["target"] is None


def test_beating_needs_rs_x_and_gain_over_dsex_sorted_by_excess():
    stocks = [
        _stock("A", close_last=105.0, rs_column="X"),
        _stock("B", close_last=120.0, rs_column="X"),
        _stock("C", close_last=130.0, rs_column="O"),
        _stock("D", close_last=100.5, rs_column="X"),   # below DSEX +1%
    ]
    out = S.signal_lists(_inputs(stocks, dsex_last=101.0), "day")
    assert [x["code"] for x in out["beating"]] == ["B", "A"]
    assert out["counts"]["beating"] == 2


def test_beating_empty_when_dsex_change_unknown():
    I = _inputs([_stock("A", rs_column="X")])
    I["dsex"] = {"dates": ["2026-11-17"], "close": [100.0]}
    assert S.signal_lists(I, "day")["beating"] == []


def test_volume_today_or_period_average():
    rv_week = [1.0] * (N - 3) + [2.5, 2.5, 1.2]   # week avg 2.07, today 1.2
    stocks = [
        _stock("A", vol_ratio=2.0),
        _stock("B", vol_ratio=1.2, rvol=rv_week),
        _stock("C", vol_ratio=1.9),
    ]
    day = S.signal_lists(_inputs(stocks), "day")
    assert [x["code"] for x in day["volume"]] == ["A"]
    week = S.signal_lists(_inputs(stocks), "week")
    assert [x["code"] for x in week["volume"]] == ["A", "B"]
    assert week["counts"]["volume"] == 2


def test_does_not_mutate_inputs():
    I = _inputs([_stock("A", signal_date="2026-11-17", rs_column="X", vol_ratio=3.0)])
    before = copy.deepcopy(I)
    S.signal_lists(I, "month")
    assert I == before


def test_bad_period_raises():
    with pytest.raises(ValueError):
        S.signal_lists(_inputs([]), "year")


# --- real fixture --------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    with open(FIXTURE) as f:
        return json.load(f)


def test_real_fixture_day_counts_match_engine(real):
    out = S.signal_lists(real, "day")
    assert out["counts"]["buys"] == real["breadth_today"]["new_buys"] == 23
    assert out["counts"]["sells"] == real["breadth_today"]["new_sells"] == 6
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_real_fixture_shape_and_sanity(real, period):
    out = S.signal_lists(real, period)
    for key in ("buys", "sells", "beating", "volume"):
        items = out[key]
        assert len(items) <= 5 and out["counts"][key] >= len(items)
        for it in items:
            assert it["code"] in real["stocks"]
            assert it["mfi"] is None or 0 <= it["mfi"] <= 100
            assert all(c["tone"] in ("up", "down", "flat", "warn") for c in it["chips"])
        if key != "beating":
            rv = [it["rvol"] or 0 for it in items]
            assert rv == sorted(rv, reverse=True)
    for it in out["buys"]:
        assert real["stocks"][it["code"]]["signal"] == "BUY"
    for it in out["beating"]:
        assert real["stocks"][it["code"]]["rs_column"] == "X"
    json.dumps(out, allow_nan=False)


def test_state_reads_column_macd_and_rsi():
    s = _stock("AAA", column="X", macd=[0.2] * (N - 1) + [0.4], macd_hist=[0.1] * (N - 1) + [0.3],
               rsi=[55.0] * (N - 1) + [72.0])
    st = S.state(s)
    assert {k: st[k] for k in ("column", "macd", "macd_dir", "rsi", "rsi_band", "rsi_dir")} == {
        "column": "X", "macd": "above", "macd_dir": "rising", "rsi": 72.0, "rsi_band": ">70", "rsi_dir": "rising"}


def test_state_falling_below_and_bands():
    s = _stock("AAA", column="O", macd=[-0.5] * N, macd_hist=[0.3] * (N - 1) + [0.1], rsi=[40.0] * (N - 1) + [28.0])
    st = S.state(s)
    assert (st["macd"], st["macd_dir"], st["rsi_band"], st["rsi_dir"]) == ("below", "falling", "<30", "falling")
    assert S._rsi_band(50.0) == ">50" and S._rsi_band(49.9) == "<50" and S._rsi_band(70.0) == ">50"
    assert S._direction([1.0, 1.0]) == "flat"


def test_state_reads_mfi_band_and_direction():
    # money flows in on the last two sessions: MFI ends high and rising
    close = [100.0 - (i % 2) for i in range(N - 2)] + [104.0, 110.0]
    s = _stock("AAA", close=close, high=[c + 1 for c in close], low=[c - 1 for c in close],
               volume=[1000.0] * (N - 2) + [5000.0, 9000.0])
    st = S.state(s)
    assert st["mfi"] is not None and st["mfi_band"] in (">80", ">50") and st["mfi_dir"] == "rising"
    assert st["mfi"] == S._mfi(s)
    assert [S._mfi_band(v) for v in (80.1, 80.0, 50.0, 49.9, 20.0, 19.9, None)] == [">80", ">50", ">50", "<50", "<50", "<20", None]


def test_state_with_missing_data_is_all_none():
    s = _stock("AAA", column=None, macd=[], macd_hist=[None], rsi=[None, None])
    s.pop("volume")
    assert S.state(s) == {"column": None, "macd": None, "macd_dir": None, "rsi": None, "rsi_band": None,
                          "rsi_dir": None, "mfi": None, "mfi_band": None, "mfi_dir": None}


def test_signal_items_carry_state():
    I = json.loads(FIXTURE.read_text())
    out = S.signal_lists(I, "week")
    items = [it for k in S.LISTS for it in out[k]]
    assert items and all(set(it["state"]) == {"column", "macd", "macd_dir", "rsi", "rsi_band", "rsi_dir",
                                                    "mfi", "mfi_band", "mfi_dir"} for it in items)
