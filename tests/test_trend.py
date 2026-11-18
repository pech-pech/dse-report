from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from dsereport import trend

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"


def _sessions(n: int) -> list[str]:
    out, d = [], date(2026, 1, 4)
    while len(out) < n:
        if d.weekday() not in (4, 5):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _inputs(closes: list[float]) -> dict:
    s = _sessions(len(closes))
    return {"asof": s[-1], "sessions": s, "dsex": {"dates": s, "close": closes}}


@pytest.fixture(scope="module")
def real():
    return json.loads(FIXTURE.read_text())


# --- helpers ------------------------------------------------------------

def test_slope_rising_falling_and_unknown():
    assert trend._slope([1, 2, 3, 4, 5, 6]) == "rising"
    assert trend._slope([6, 5, 4, 3, 2, 1]) == "falling"
    assert trend._slope([None, 2, 3, 4, 5, 6]) is None
    assert trend._slope([1, 2]) is None


def test_dist_pct():
    assert trend._dist_pct(110.0, 100.0) == 10.0
    assert trend._dist_pct(90.0, 100.0) == -10.0
    assert trend._dist_pct(90.0, None) is None


def test_hist_run_counts_consecutive_moves():
    assert trend._hist_run([None, 1, 2, 3, 4]) == 3
    assert trend._hist_run([5, 4, 3, 3.5]) == 1
    assert trend._hist_run([1, 4, 3, 2, 1]) == -3
    assert trend._hist_run([1, 1]) == 0
    assert trend._hist_run([None, None]) == 0


def test_last_cross_finds_latest_sign_change():
    dates = ["d1", "d2", "d3", "d4", "d5"]
    a = [1, 3, 3, 1, 3]
    b = [2, 2, 2, 2, 2]
    assert trend._last_cross(dates, a, b) == ("above", "d5")
    assert trend._last_cross(dates, a[:4], b[:4]) == ("below", "d4")
    assert trend._last_cross(dates, [3, 3], [2, 2]) is None
    assert trend._last_cross(dates, [None, 3], [2, 2]) is None


def test_headline_variants():
    allup = {"ema20": 1.0, "ema50": 2.0, "ema200": 3.0}
    assert trend._headline(allup) == "Above all three averages"
    assert trend._headline({k: -v for k, v in allup.items()}) == "Below all three averages"
    assert trend._headline({"ema20": 1, "ema50": 1, "ema200": -1}) == \
        "Above two of three averages; EMA200 overhead"
    assert trend._headline({"ema20": 1, "ema50": -1, "ema200": -1}) == \
        "Above one of three averages; EMA50 and EMA200 overhead"
    assert trend._headline({"ema20": -1, "ema50": 1, "ema200": 1}) == \
        "Above two of three averages; EMA20 overhead"
    assert trend._headline({"ema20": None, "ema50": None, "ema200": None}) == "Not enough history for averages"
    assert trend._headline({"ema20": 1, "ema50": 1, "ema200": None}) == "Above both available averages"


# --- the block on hand-made data ------------------------------------------

def test_steady_uptrend_block():
    closes = [1000 + i for i in range(300)]
    I = _inputs(closes)
    before = copy.deepcopy(I)
    b = trend.trend_block(I, "day")
    assert I == before
    assert len(b["dates"]) == 60 and len(b["close"]) == 60 and len(b["ema200"]) == 60
    assert len(b["macd"]["line"]) == 60 and len(b["macd"]["hist"]) == 60
    assert b["dates"][-1] == I["sessions"][-1]
    last = b["last"]
    assert last["close"] == 1299.0
    # EMA of a straight line lags by (n-1)/2
    assert last["ema20"] == pytest.approx(1289.5, abs=0.01)
    assert last["ema50"] == pytest.approx(1274.5, abs=0.01)
    assert all(v == "rising" for v in last["slope"].values())
    assert all(v > 0 for v in last["dist_pct"].values())
    assert b["cross"] is None
    st = b["macd_state"]
    assert st["above_zero"] is True
    assert b["headline"] == "Above all three averages"
    assert b["period_sessions"] == 1
    assert "above EMA20" in b["sentence"] and "EMA200" in b["sentence"]
    assert "1,299.0" in b["sentence"]
    json.dumps(b, allow_nan=False)


def test_turn_down_below_ema200_is_said():
    rise = [1000 + i + 0.005 * i * i for i in range(250)]
    closes = rise + [rise[-1] - 15 * i for i in range(1, 51)]
    b = trend.trend_block(_inputs(closes), "week")
    last = b["last"]
    assert last["close"] < last["ema200"]
    assert last["dist_pct"]["ema200"] < 0
    assert b["headline"] == "Below all three averages"
    assert "below EMA200" in b["sentence"] or "below all three" in b["sentence"]
    assert b["cross"]["kind"] == "EMA20 below EMA50"
    assert b["cross"]["date"] in b["dates"]
    st = b["macd_state"]
    assert st["above_zero"] is False
    assert st["last_signal_cross"]["kind"] == "below"
    assert last["slope"]["ema20"] == "falling"
    assert 1 <= b["period_sessions"] <= 5


def test_short_history_has_nones_and_no_crash():
    closes = [100 + (i % 7) for i in range(40)]
    b = trend.trend_block(_inputs(closes), "month")
    assert len(b["dates"]) == 40
    assert b["last"]["ema200"] is None and b["last"]["ema50"] is None
    assert b["last"]["dist_pct"]["ema200"] is None
    assert b["last"]["slope"]["ema200"] is None
    assert b["ema200"] == [None] * 40
    assert "not enough history" in b["sentence"].lower() or "EMA200" not in b["headline"]
    json.dumps(b, allow_nan=False)


def test_empty_dsex():
    b = trend.trend_block({"asof": "2026-11-17", "sessions": [], "dsex": {"dates": [], "close": []}}, "day")
    assert b["dates"] == [] and b["last"]["close"] is None
    assert b["headline"] == "Not enough history for averages"


# --- real fixture ---------------------------------------------------------

@pytest.mark.parametrize("p", ["day", "week", "month"])
def test_real_fixture_shape_and_consistency(real, p):
    b = trend.trend_block(real, p)
    json.dumps(b, allow_nan=False)
    assert len(b["dates"]) == 60
    assert b["dates"][-1] == real["asof"]
    assert all(v is not None for v in b["ema200"])
    last = b["last"]
    assert last["close"] == round(real["dsex"]["close"][-1], 2)
    for k in ("ema20", "ema50", "ema200"):
        above = last["close"] > last[k]
        assert (last["dist_pct"][k] > 0) == above
        assert last["slope"][k] in ("rising", "falling")
        word = "above" if above else "below"
        assert f"{word} {k.upper()}" in b["sentence"] or f"{word} all three" in b["sentence"]
    st = b["macd_state"]
    assert st["above_signal"] == (b["macd"]["line"][-1] > b["macd"]["signal"][-1])
    assert st["above_zero"] == (b["macd"]["line"][-1] > 0)
    assert isinstance(st["hist_run"], int)
    if b["cross"] is not None:
        assert b["cross"]["date"] in b["dates"]
