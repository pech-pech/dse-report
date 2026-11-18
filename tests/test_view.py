"""The analyst view: grade points, confidence, targets and the WHY-CONTRACT shape, from the setup's own numbers."""
import json
import math
from pathlib import Path

import pytest

from dsereport import build, view

KEYS = ("one_box", "squeeze", "macd_above_signal", "above_ema50", "above_ema200", "mfi_rising", "sector_bp_rising")
S = {"ema50": [95.0], "ema200": 80.0}
BANK_O = "Caution: the Bank bullish percent is in a falling (O) column."


def _item(met=7, rvol=1.0, caution=None, trigger_pct=1.0, target=None, objective_if=110.0, resistance=104.0,
          cancel=90.0, close=99.0, trigger=100.0, off=(), pattern="Double Top buy", pf_cols=None):
    conds = [{"key": k, "label": k, "met": i < met and k not in off, "help": ""} for i, k in enumerate(KEYS)]
    return {"code": "ACME", "sector": "Bank", "close": close, "trigger": trigger, "trigger_pct": trigger_pct,
            "target": target, "objective_if": objective_if, "resistance": resistance, "cancel": cancel,
            "rvol": rvol, "caution": caution, "conditions": conds, "pattern": pattern,
            "pf_cols": pf_cols if pf_cols is not None else [["X", 90.0, 99.0, 4]]}


def _view(item=None, s=S, mfi=(70.0, 60.0), sector_col=None):
    return view.analyst_view(s, item or _item(), mfi[0], mfi[1], sector_col)


def _pillar(v, name):
    return next(p for p in v["pillars"] if p["name"] == name)


# ---- grading rules (unchanged) --------------------------------------------------------------------------

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


# ---- badge, verdict, sub ----------------------------------------------------------------------------------

def test_shape_keeps_grading_keys_and_drops_the_old_ones():
    v = _view(_item(target=125.0, rvol=2.0))
    assert set(v) == {"badge", "tone", "verdict", "sub", "thesis", "pillars", "plan", "plan_note", "change_view",
                      "method", "grade", "confidence", "points", "targets"}
    assert v["badge"] == v["grade"] == "A" and v["confidence"] == "High" and v["points"] == 8
    assert v["method"] == "Rules-based rating from the chart's numbers. Not investment advice."


@pytest.mark.parametrize("met,caution,badge,tone,verdict", [
    (7, None, "A", "up", "Buy on a close at 100.0"),
    (6, None, "B", "up", "Buy on a close at 100.0"),
    (7, "Caution: x.", "B", "up", "Buy on a close at 100.0, half size"),
    (4, None, "C", "flat", "Watch for a close at 100.0"),
    (3, BANK_O, "D", "down", "Watch for a close at 100.0"),
])
def test_verdict_variants(met, caution, badge, tone, verdict):
    v = _view(_item(met=met, caution=caution))
    assert (v["badge"], v["tone"], v["verdict"]) == (badge, tone, verdict)
    assert len(v["verdict"]) <= 48


def test_sub_reads_confidence_and_points():
    assert _view(_item(met=6))["sub"] == "Medium confidence · 6 evidence points"
    assert _view(_item(met=1))["sub"] == "Low confidence · 1 evidence point"


# ---- thesis -----------------------------------------------------------------------------------------------

def test_thesis_strong_setup_aims_first_at_t1():
    v = _view(_item(met=7, rvol=2.0))
    assert v["thesis"] == ("A close at 100.0 completes a Double Top buy with trend, momentum, money flow, volume, "
                           "the sector and a tight range behind it. We would buy the print, not the anticipation, "
                           "and aim first at 104.0 where the last rally stalled.")


def test_thesis_without_t1_aims_at_t2_and_without_t2_just_buys():
    assert _view(_item(resistance=None))["thesis"].endswith("not the anticipation, and aim at 110.0.")
    assert _view(_item(resistance=None, objective_if=None))["thesis"].endswith("buy the print, not the anticipation.")


def test_thesis_caution_branch_names_what_is_against_it():
    item = _item(met=6, off=("above_ema200", "sector_bp_rising"), rvol=1.2,
                 caution=BANK_O[:-1] + " and the price is below its EMA200 (101.00).")
    v = _view(item, s={"ema50": [95.0], "ema200": 101.0}, sector_col="O")
    assert "; the Bank bullish percent falling and the price under its EMA200 (101.0) are against it." in v["thesis"]
    v = _view(_item(met=7, caution="Caution: thin float."))       # a caution from elsewhere is quoted
    assert "; thin float is against it." in v["thesis"]


def test_thesis_weak_setup_waits():
    v = _view(_item(met=1, rvol=0.5), mfi=(None, None))
    assert v["thesis"] == ("A close at 100.0 completes a Double Top buy with no other pillar behind it. "
                           "We would wait for the print and more support before acting.")


# ---- pillars ----------------------------------------------------------------------------------------------

def test_pillars_in_order_and_every_mark_valid():
    v = _view()
    assert [p["name"] for p in v["pillars"]] == ["Pattern", "Trend", "Momentum", "Money flow", "Volume", "Sector",
                                                 "Volatility"]
    assert all(p["mark"] in ("up", "down", "flat") and p["reading"] for p in v["pillars"])


def test_pattern_pillar():
    assert _pillar(_view(), "Pattern") == {"name": "Pattern", "mark": "up",
                                           "reading": "Double Top, one box (+1.0%) from the buy"}
    p = _pillar(_view(_item(pattern="P&F buy signal", close=None)), "Pattern")
    assert p["reading"] == "One box from a P&F buy signal"


def test_trend_pillar_up_flat_down():
    assert _pillar(_view(), "Trend") == {"name": "Trend", "mark": "up", "reading": "Above EMA50 95.0 and EMA200 80.0"}
    flat = _pillar(_view(_item(off=("above_ema200",))), "Trend")
    assert (flat["mark"], flat["reading"]) == ("flat", "Above EMA50 95.0, below EMA200 80.0")
    flat = _pillar(_view(_item(off=("above_ema50",))), "Trend")
    assert (flat["mark"], flat["reading"]) == ("flat", "Below EMA50 95.0, above EMA200 80.0")
    down = _pillar(_view(_item(off=("above_ema50", "above_ema200")), s={}), "Trend")
    assert (down["mark"], down["reading"]) == ("down", "Below EMA50 and EMA200")


def test_momentum_pillar():
    assert _pillar(_view(), "Momentum")["mark"] == "up"
    p = _pillar(_view(_item(off=("macd_above_signal",))), "Momentum")
    assert (p["mark"], p["reading"]) == ("down", "MACD below signal")


def test_money_flow_pillar():
    assert _pillar(_view(), "Money flow") == {"name": "Money flow", "mark": "up", "reading": "MFI 70 (60 a week ago)"}
    p = _pillar(_view(_item(off=("mfi_rising",)), mfi=(40.0, 50.0)), "Money flow")
    assert (p["mark"], p["reading"]) == ("down", "MFI 40 (50 a week ago)")
    p = _pillar(_view(mfi=(None, 50.0)), "Money flow")
    assert (p["mark"], p["reading"]) == ("flat", "MFI not available")


@pytest.mark.parametrize("rvol,mark,reading", [
    (1.5, "up", "1.5× average"), (1.2, "flat", "1.2× average"), (1.0, "flat", "1.0× average"),
    (0.6, "down", "0.6× average"), (None, "flat", "Volume not available"),
])
def test_volume_pillar(rvol, mark, reading):
    p = _pillar(_view(_item(rvol=rvol)), "Volume")
    assert (p["mark"], p["reading"]) == (mark, reading)


def test_sector_pillar_x_o_unknown():
    assert _pillar(_view(), "Sector") == {"name": "Sector", "mark": "up", "reading": "Bank BP rising"}
    p = _pillar(_view(_item(off=("sector_bp_rising",), caution=BANK_O)), "Sector")      # read back from the caution
    assert (p["mark"], p["reading"]) == ("down", "Bank BP in a falling column")
    p = _pillar(_view(_item(off=("sector_bp_rising",)), sector_col="O"), "Sector")      # passed in by setups
    assert p["mark"] == "down"
    item = {**_item(off=("sector_bp_rising",)), "sector": None}
    p = _pillar(_view(item), "Sector")
    assert (p["mark"], p["reading"]) == ("flat", "Its sector BP column not known")


def test_volatility_pillar():
    assert _pillar(_view(), "Volatility") == {"name": "Volatility", "mark": "up",
                                              "reading": "Squeeze: tightest in 60 sessions"}
    p = _pillar(_view(_item(off=("squeeze",))), "Volatility")
    assert (p["mark"], p["reading"]) == ("flat", "No squeeze: range is not unusually tight")


# ---- plan, plan_note, change_view ---------------------------------------------------------------------------

def test_plan_tiles_with_t1():
    assert _view()["plan"] == [
        {"label": "Entry", "value": 100.0, "pct": 1.0, "tone": "acc"},
        {"label": "Target 1", "value": 104.0, "pct": 5.1, "tone": "up"},
        {"label": "Target 2", "value": 110.0, "pct": 11.1, "tone": "up"},
        {"label": "Stop", "value": 90.0, "pct": -9.1, "tone": "down"},
    ]


def test_plan_tiles_without_t1_or_stop():
    plan = _view(_item(resistance=None, cancel=None))["plan"]
    assert [(p["label"], p["tone"]) for p in plan] == [("Entry", "acc"), ("Target", "up")]


@pytest.mark.parametrize("kw,mfi,risk", [
    ({"met": 6, "off": ("sector_bp_rising",), "caution": BANK_O}, (70.0, 60.0), "the Bank bullish percent falling"),
    ({"off": ("macd_above_signal",)}, (70.0, 60.0), "momentum has not turned, MACD is below its signal line"),
    ({"off": ("mfi_rising",)}, (50.0, 60.0), "money flow is not rising"),
    ({"rvol": 0.7}, (70.0, 60.0), "volume is below average, and thin breakouts often fail"),
    ({}, (70.0, 60.0), "a failed breakout that retests 99.0"),
    ({"pf_cols": []}, (70.0, 60.0), "a failed breakout that retests the old top"),
])
def test_plan_note_names_the_first_substantive_risk(kw, mfi, risk):
    v = _view(_item(**kw), mfi=mfi)
    assert v["plan_note"] == f"Reward/risk 1.0 : 1. Main risk: {risk}."


def test_plan_note_without_reward_risk():
    assert _view(_item(cancel=None))["plan_note"] == "Main risk: a failed breakout that retests 99.0."


def test_change_view_with_and_without_ema50():
    assert _view()["change_view"] == "A close below 95.0 (EMA50) before the trigger, or 90.0 (P&F sell) after it."
    assert _view(s={"ema200": 80.0})["change_view"] == "A close below 90.0 (P&F sell) after the trigger."
    assert _view(_item(cancel=None))["change_view"] == "A close below 95.0 (EMA50) before the trigger."
    assert _view(_item(cancel=None), s={})["change_view"] is None


# ---- the real report ----------------------------------------------------------------------------------------

def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def test_real_report_setups_carry_a_clean_view():
    I = json.loads((Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json").read_text())
    r = build.build_report(I, None, built_at="2026-11-17T11:05:00Z")
    assert r["setups"]
    for s in r["setups"]:
        v = s["view"]
        assert v["badge"] in "ABCD" and v["tone"] in ("up", "down", "flat")
        assert v["confidence"] in ("High", "Medium", "Low") and len(v["verdict"]) <= 48
        assert len(v["pillars"]) == 7 and all(p["mark"] in ("up", "down", "flat") for p in v["pillars"])
        assert v["thesis"].count(". ") == 1 and v["plan_note"] and v["change_view"]
        assert not {"why", "risks", "note"} & set(v)
        for text in _strings(v):
            assert "None" not in text and "nan" not in text.lower() and "FoodAllied" not in text
        assert all(x is None or math.isfinite(x) for x in v["targets"].values() if not isinstance(x, str))
    by_code = {s["code"]: s["view"] for s in r["setups"]}
    meg = by_code["MEGHNAPET"]
    assert (meg["verdict"], meg["sub"]) == ("Buy on a close at 76.0", "Medium confidence · 7 evidence points")
    assert _pillar(meg, "Sector")["reading"] == "Food & Allied BP rising"
    assert meg["change_view"] == "A close below 72.1 (EMA50) before the trigger, or 64.0 (P&F sell) after it."
    mid = by_code["MIDLANDBNK"]
    assert mid["verdict"] == "Buy on a close at 18.0, half size" and _pillar(mid, "Sector")["mark"] == "down"
