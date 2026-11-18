"""The analyst view: grade points, confidence, targets and the wording, from the setup's own numbers."""
import json
import math
from pathlib import Path

from dsereport import build, view

KEYS = ("one_box", "squeeze", "macd_above_signal", "above_ema50", "above_ema200", "mfi_rising", "sector_bp_rising")


def _item(met=7, rvol=1.0, caution=None, trigger_pct=1.0, target=None, objective_if=110.0, resistance=104.0,
          cancel=90.0, close=99.0, trigger=100.0):
    conds = [{"key": k, "label": k, "met": i < met, "help": ""} for i, k in enumerate(KEYS)]
    return {"code": "ACME", "sector": "Bank", "close": close, "trigger": trigger, "trigger_pct": trigger_pct,
            "target": target, "objective_if": objective_if, "resistance": resistance, "cancel": cancel,
            "rvol": rvol, "caution": caution, "conditions": conds, "pattern": "Double Top buy"}


def test_grade_points_and_letters():
    assert view.grade(_item(met=7)) == ("A", 7)
    assert view.grade(_item(met=6, rvol=1.5)) == ("A", 7)                 # volume confirms
    assert view.grade(_item(met=7, caution="Caution: x.")) == ("B", 6)
    assert view.grade(_item(met=6, trigger_pct=3.5)) == ("B", 5)          # far trigger
    assert view.grade(_item(met=4)) == ("C", 4)
    assert view.grade(_item(met=2)) == ("D", 2)


def test_targets_and_reward_risk():
    t = view.targets(_item())
    assert (t["entry"], t["t1"], t["t2"], t["stop"]) == (100.0, 104.0, 110.0, 90.0)
    assert t["rr"] == 1.0 and t["t2_basis"] == "P&F count if triggered"
    t = view.targets(_item(target=125.0))
    assert t["t2"] == 125.0 and t["t2_basis"] == "P&F target" and t["rr"] == 2.5
    assert view.targets(_item(resistance=99.0))["t1"] is None              # not above the entry
    assert view.targets(_item(resistance=120.0))["t1"] is None             # beyond the objective
    assert view.targets(_item(cancel=None))["rr"] is None


def test_confidence():
    assert view.confidence("A", 2.0) == "High"
    assert view.confidence("A", 1.9) == "Medium"
    assert view.confidence("A", None) == "Medium"
    assert view.confidence("B", 3.0) == "Medium"
    assert view.confidence("C", 3.0) == "Low"


def test_view_wording_and_risks():
    v = view.analyst_view({"ema50": [95.0], "ema200": 80.0}, _item(target=125.0, rvol=2.0), 70.0, 60.0)
    assert v["grade"] == "A" and v["confidence"] == "High"
    assert v["note"].startswith("We rate ACME A with high confidence.")
    assert "reward/risk of 2.5 to 1" in v["note"] and "1.0% above the close" in v["note"]
    assert v["why"][0].startswith("Double Top buy one box away")
    assert any(w.startswith("Volume: 2.0 times") for w in v["why"])
    assert v["risks"][0].startswith("A failed breakout")                  # nothing against it in the evidence
    assert "Not investment advice" in v["method"]


def test_weak_setup_lists_what_is_missing():
    item = _item(met=3, rvol=0.6, caution="Caution: the Bank bullish percent is in a falling (O) column.")
    v = view.analyst_view({}, item, 40.0, 50.0)
    assert v["grade"] == "D" and v["confidence"] == "Low"
    assert v["risks"][0] == "The Bank bullish percent is in a falling (O) column."
    assert any("below average" in r for r in v["risks"])
    assert "Main risk: the Bank bullish percent" in v["note"]


def test_real_report_setups_carry_a_clean_view():
    I = json.loads((Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json").read_text())
    r = build.build_report(I, None, built_at="2026-11-17T11:05:00Z")
    assert r["setups"]
    for s in r["setups"]:
        v = s["view"]
        assert v["grade"] in "ABCD" and v["confidence"] in ("High", "Medium", "Low")
        assert v["why"] and v["risks"] and v["note"]
        text = json.dumps(v)
        assert "None" not in text and "nan" not in text.lower()
        assert all(x is None or math.isfinite(x) for x in v["targets"].values() if not isinstance(x, str))
