from __future__ import annotations

import copy
import json
from pathlib import Path

from dsereport import setups

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"
N = 30


def _stock(code="AAA", **over):
    close = [10.0 + 0.1 * i for i in range(N)]          # steady rise: 10.0 .. 12.9
    close[12] = close[11] - 0.5                          # one down day, inside MFI's window 6 bars ago only
    s = {
        "code": code, "sector": "Bank", "close": close,
        "high": [c + 0.1 for c in close], "low": [c - 0.1 for c in close],
        "volume": [1000.0 + 50 * i for i in range(N)],
        "ema200": 11.0, "ema50": [12.0] * N,
        "macd": [0.2] * N, "macd_signal": [0.1] * N,
        "bandwidth": [0.2] * (N - 1) + [0.1],
        "signal": "SELL", "pattern": "Double Bottom", "signal_date": "2026-10-01",
        "buy_at": 13.5, "sell_at": 11.5, "target": 16.0, "to_buy": 1, "stale": False,
        "vol_ratio": 1.5,
        "pf": {"cols": [["X", 11.5, 13.0, 4], ["O", 12.0, 12.5, 2], ["X", 12.0, 13.0, 3]], "reversal": 3},
    }
    s.update(over)
    return s


def _inputs(*stocks, sector_col="X"):
    return {"asof": "2026-11-17", "stocks": {s["code"]: s for s in stocks},
            "sector_bp": {"Bank": {"column": sector_col, "bp": 55.0},
                          "Fuel": {"column": "O", "bp": 30.0}}}


def _cond(item, key):
    return next(c for c in item["conditions"] if c["key"] == key)


def test_all_seven_conditions_met():
    item = setups.find_setups(_inputs(_stock()))[0]
    assert item["score"] == 7
    assert [c["key"] for c in item["conditions"]] == list(setups.CONDITION_KEYS)
    assert all(c["met"] and c["label"] and c["help"].endswith(".") for c in item["conditions"])
    assert item["caution"] is None
    assert item["close"] == 12.9 and item["trigger"] == 13.5 and item["target"] == 16.0 and item["cancel"] == 11.5
    assert item["trigger_pct"] == 4.7 and item["target_pct"] == 24.0 and item["cancel_pct"] == -10.9
    assert item["rvol"] == 1.5 and item["pf_cols"][-1] == ["X", 12.0, 13.0, 3]


def test_labels_match_contract():
    labels = [c["label"] for c in setups.find_setups(_inputs(_stock()))[0]["conditions"]]
    assert labels == ["One box from a P&F buy", "Bollinger squeeze", "MACD above signal", "Above EMA50",
                      "Above EMA200", "MFI rising", "Sector bullish % rising"]


def test_unmet_conditions_and_caution():
    s = _stock(ema200=20.0, ema50=[14.0] * N, macd=[0.0] * N, bandwidth=[0.1] * (N - 1) + [0.2],
               volume=[1000.0] * N, close=[12.0] * N, high=[12.1] * N, low=[11.9] * N, sector="Fuel")
    item = setups.find_setups(_inputs(s))[0]
    assert item["score"] == 1                     # only one_box
    for key in ("squeeze", "macd_above_signal", "above_ema50", "above_ema200", "mfi_rising", "sector_bp_rising"):
        assert _cond(item, key)["met"] is False
    assert "Fuel" in item["caution"] and "EMA200" in item["caution"]
    assert item["reasoning"][-1].startswith("Caution")


def test_caution_only_below_ema200():
    item = setups.find_setups(_inputs(_stock(ema200=13.0)))[0]
    assert item["caution"] is not None and "Bank" not in item["caution"]


def test_filters_stale_far_short_and_missing_trigger():
    good = _stock("GOOD")
    stale = _stock("STALE", stale=True)
    far = _stock("FAR", to_buy=2)
    short = _stock("SHORT", close=[10.0] * 5)
    notrig = _stock("NOTRIG", buy_at=None)
    out = setups.find_setups(_inputs(good, stale, far, short, notrig))
    assert [i["code"] for i in out] == ["GOOD"]


def test_rank_by_score_then_rvol_and_k():
    a = _stock("A", vol_ratio=1.0)
    b = _stock("B", vol_ratio=3.0)
    c = _stock("C", vol_ratio=9.0, ema200=99.0)       # lower score despite high rvol
    out = setups.find_setups(_inputs(a, b, c), k=2)
    assert [i["code"] for i in out] == ["B", "A"]
    assert [i["code"] for i in setups.find_setups(_inputs(a, b, c))] == ["B", "A", "C"]


def test_missing_target_is_skipped_and_said():
    item = setups.find_setups(_inputs(_stock(target=0)))[0]
    assert item["target"] is None and item["target_pct"] is None
    assert any("no P&F price objective" in s for s in item["reasoning"])


def test_downside_objective_is_not_a_target():
    item = setups.find_setups(_inputs(_stock(target=9.0)))[0]
    assert item["target"] is None and item["target_pct"] is None
    assert "objective of 9.0 comes from the current sell signal" in item["reasoning"][1]


def test_missing_sell_at():
    item = setups.find_setups(_inputs(_stock(sell_at=None)))[0]
    assert item["cancel"] is None and item["cancel_pct"] is None


def test_reasoning_names_pattern_and_numbers():
    item = setups.find_setups(_inputs(_stock()))[0]
    r = item["reasoning"]
    assert 2 <= len(r) <= 4
    assert "a rise to 13.5 would give a Double Top buy" in r[0]
    assert "16.0" in r[1] and "11.5" in r[1]
    assert "MACD is above its signal line" in r[2]


def test_triple_top_and_generic_buy_wording():
    cols = [["X", 11.5, 13.0, 4], ["O", 12.0, 12.5, 2], ["X", 12.0, 13.0, 3],
            ["O", 12.0, 12.5, 2], ["X", 12.0, 13.0, 3]]
    s = _stock(pf={"cols": cols, "reversal": 3})
    assert "Triple Top buy" in setups.find_setups(_inputs(s))[0]["reasoning"][0]
    s2 = _stock(pf={"cols": [["X", 12.0, 13.0, 3]], "reversal": 3})
    assert "a P&F buy signal" in setups.find_setups(_inputs(s2))[0]["reasoning"][0]


def test_none_values_do_not_crash():
    s = _stock(macd=[None] * N, macd_signal=[None] * N, bandwidth=[None] * N, ema50=[None] * N, ema200=None)
    item = setups.find_setups(_inputs(s))[0]
    assert item["score"] == 3                       # one_box, mfi_rising, sector
    json.dumps(item)


def test_does_not_mutate_inputs():
    I = _inputs(_stock())
    before = copy.deepcopy(I)
    item = setups.find_setups(I)[0]
    item["pf_cols"].append(["O", 1, 2, 3])
    assert I == before


def test_real_fixture_shape():
    I = json.loads(FIXTURE.read_text())
    out = setups.find_setups(I)
    assert 1 <= len(out) <= 4
    scores = [(i["score"], i["rvol"] or 0) for i in out]
    assert scores == sorted(scores, reverse=True)
    for i in out:
        assert I["stocks"][i["code"]]["to_buy"] == 1
        assert i["trigger"] > i["close"]
        assert i["target"] is None or i["target"] > i["trigger"]
        assert len(i["conditions"]) == 7 and _cond(i, "one_box")["met"]
        assert 2 <= len(i["reasoning"]) <= 4
        assert (i["caution"] is None) == (not i["reasoning"][-1].startswith("Caution"))
    json.dumps(out, allow_nan=False)


def test_pending_objective_and_resistance_shown_when_no_upside_target():
    s = _stock(target=9.0, pending={"objective": 17.5, "resistance": 14.0})
    item = setups.find_setups(_inputs(s))[0]
    assert item["target"] is None
    assert item["objective_if"] == 17.5 and item["resistance"] == 14.0
    assert item["objective_if_pct"] is not None and item["resistance_pct"] is not None
    assert "If 13.5 triggers, the P&F count points to about 17.5" in item["reasoning"][1]
    assert "resistance first at 14.0" in item["reasoning"][1]


def test_pending_objective_ignored_when_engine_target_exists():
    item = setups.find_setups(_inputs(_stock(pending={"objective": 17.5, "resistance": 14.0})))[0]
    assert item["target"] == 16.0 and item["objective_if"] is None
    assert "P&F count gives a target of 16.0" in item["reasoning"][1]


def test_pending_levels_at_or_below_trigger_are_dropped():
    s = _stock(target=None, pending={"objective": 13.0, "resistance": 13.5})
    item = setups.find_setups(_inputs(s))[0]
    assert item["objective_if"] is None and item["resistance"] is None
    assert "no P&F price objective" in item["reasoning"][1]


def test_objective_without_resistance_reads_cleanly():
    item = setups.find_setups(_inputs(_stock(target=None, pending={"objective": 17.5, "resistance": None})))[0]
    assert item["reasoning"][1].endswith("(" + item["reasoning"][1].split("(")[-1])
    assert "resistance" not in item["reasoning"][1]
