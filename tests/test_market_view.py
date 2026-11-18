"""The market cards' "Why?" views: pillar rules, badges and wording, on small blocks and on the real 17 Nov report."""
import json
import os
import re

import pytest

from dsereport import build, market_view as mv, schema

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "inputs_2026-11-17.json")


def _flow(**kw):
    base = {"sessions": 1, "adv": 262, "dec": 77, "unch": 44, "turnover_cr": 840.9, "turnover_avg_cr": 840.9,
            "vs_avg20": 1.59, "in_cr": 523.7, "out_cr": 288.9, "net_cr": 234.8, "last14": [1.0] * 11 + [-1.0] * 3,
            "inflow_sessions_14": 11}
    return {**base, **kw}


def _market(**pf):
    base = {"status": "BUY", "column": "X", "next_box": 5504.0, "reverse_at": 5472.0, "stop": 5440.0,
            "target": 5600.0, "trend": "bear", "trend_level": 5688.0}
    return {"dsex": {"close": 5496.73, "chg_pts": 33.44, "chg_pct": 0.61},
            "pf": {**base, **pf}, "bp": {"value": 34.0, "column": "X"}}


def _trend(dist=(1.17, 0.3, 0.82), above_signal=True, above_zero=False, run=10):
    return {"last": {"ema20": 5433.0, "dist_pct": dict(zip(mv.AVERAGES, dist))},
            "macd_state": {"above_signal": above_signal, "above_zero": above_zero, "hist_run": run}}


def _signals(buys=23, sells=6, beating=104, volume=104):
    return {"counts": {"buys": buys, "sells": sells, "beating": beating, "volume": volume}}


def _sectors(rows=None):
    rows = rows or [{"sector": "ServRealEst", "chg_pct": 3.67, "bp_column": "X", "net_cr": 21.0},
                    {"sector": "Bank", "chg_pct": 1.59, "bp_column": "O", "net_cr": 87.1},
                    {"sector": "Misc", "chg_pct": 1.2, "bp_column": "X", "net_cr": 5.0},
                    {"sector": "SME Sector", "chg_pct": -0.88, "bp_column": "O", "net_cr": -1.0}]
    return {"rows": rows, "highlights": []}


def _period(**kw):
    base = {"market": _market(), "trend": _trend(), "flow": _flow(), "sectors": _sectors(), "signals": _signals()}
    return {**base, **kw}


def _marks(view):
    return {p["name"]: p["mark"] for p in view["pillars"]}


# ---- badge and shape -----------------------------------------------------

@pytest.mark.parametrize("marks, badge, tone", [(["up", "up", "down"], "▲", "up"), (["down", "down", "up"], "▼", "down"),
                                                (["up", "down", "flat"], "◆", "flat"), (["flat"] * 3, "◆", "flat")])
def test_badge_follows_the_majority_of_marks(marks, badge, tone):
    pillars = [mv._pillar(str(i), m, "r") for i, m in enumerate(marks)]
    v = mv._view(pillars, "v", "t", [], None, "c")
    assert (v["badge"], v["tone"]) == (badge, tone)
    assert v["sub"] == f"{marks.count('up')} of 3 pillars up"


def test_too_few_pillars_gives_no_view():
    p = _period(flow={}, market={}, signals={})
    assert mv.summary_view("day", p) is None
    assert mv.flow_view("day", p) is None


def test_missing_inputs_drop_their_pillar_only():
    p = _period(market={"dsex": {"close": 5496.73, "chg_pts": 33.44, "chg_pct": 0.61}})
    v = mv.summary_view("day", p)
    assert "Bullish %" not in _marks(v) and len(v["pillars"]) == 4


def test_verdicts_fit_and_fall_back(report):
    assert report["periods"]["day"]["views"]["sectors"]["verdict"] == "17 of 20 sectors up"   # leader does not fit
    assert mv._fit("x" * 60, "short") == "short"
    assert len(mv._fit("x" * 60)) == mv.MAX_VERDICT


# ---- summary -------------------------------------------------------------

def test_summary_pillars_and_verdict():
    v = mv.summary_view("day", _period())
    assert _marks(v) == {"Breadth": "up", "Bullish %": "up", "Money flow": "up", "Turnover": "up", "Signals": "up"}
    assert v["verdict"] == "Broad advance, money flowing in" and v["badge"] == "▲"
    assert [t["label"] for t in v["plan"]] == ["DSEX close", "Change"] and v["plan"][1]["pct"] == 0.61


def test_summary_down_market():
    flow = _flow(adv=90, dec=250, net_cr=-120.0, vs_avg20=0.7)
    p = _period(flow=flow, market={**_market(), "bp": {"value": 60.0, "column": "O"}}, signals=_signals(3, 20))
    v = mv.summary_view("week", p)
    assert set(_marks(v).values()) == {"down"} and v["badge"] == "▼"
    assert v["verdict"] == "Broad decline, money flowing out"
    assert "90 advances" not in v["thesis"] and "this week" in v["thesis"]
    assert v["change_view"].startswith("More stocks rising than falling")


def test_turnover_in_line_is_flat():
    assert mv._p_turnover(_flow(vs_avg20=1.005))["mark"] == "flat"
    assert "in line" in mv._p_turnover(_flow(vs_avg20=1.005))["reading"]


def test_narrow_breadth_is_not_called_broad():
    assert mv._breadth_words(_flow(adv=120, dec=100)) == "More gainers than losers"
    assert mv._breadth_words(_flow(adv=100, dec=100)) == "Even breadth"


# ---- trend ---------------------------------------------------------------

def test_trend_matches_the_mockup():
    v = mv.trend_view("day", _period())
    assert _marks(v) == {"P&F": "up", "Averages": "up", "Momentum": "up", "Breadth": "up", "Trend line": "down"}
    assert v["verdict"] == "Recovering, under resistance" and v["sub"] == "4 of 5 pillars up"
    assert v["thesis"].startswith("Short-term trend has turned up, but DSEX still sits below its P&F resistance "
                                  "line at 5,688.")
    assert v["change_view"] == "A box at 5,472 reverses the P&F column; a close above 5,688 breaks the resistance line."
    assert [(t["label"], t["tone"]) for t in v["plan"]] == [("P&F reversal", "down"), ("Next box", "up"),
                                                           ("Trend line", "flat")]


def test_trend_pillar_rules():
    assert mv._p_averages(_trend(dist=(1.0, -0.5, None)))["reading"] == "Above EMA20; below EMA50"
    assert mv._p_averages(_trend(dist=(-1.0, -0.5, -2.0)))["mark"] == "down"
    assert mv._p_momentum(_trend(above_signal=False, run=-1))["reading"] == \
        "MACD below signal, below zero; histogram falling 1 session"
    assert mv._p_pf(_market(status="BUY", column="O"))["mark"] == "flat"
    assert mv._p_pf(_market(status="SELL", column="O"))["mark"] == "down"
    assert mv._p_trend_line(_market(trend="bull", trend_level=5300.0))["mark"] == "up"
    assert mv._p_trend_line(_market(trend=None)) is None


def test_downtrend_above_support():
    p = _period(market={**_market(status="SELL", column="O", trend="bull", trend_level=5300.0),
                        "bp": {"value": 30.0, "column": "O"}},
                trend=_trend(dist=(-1.0, -0.5, -0.2), above_signal=False))
    v = mv.trend_view("day", p)
    assert v["badge"] == "▼"
    assert "but DSEX still holds above its P&F support line at 5,300" in v["thesis"]
    assert v["plan"][0]["tone"] == "up" and v["plan"][1]["tone"] == "down"   # O column: reversal is up


# ---- flow ----------------------------------------------------------------

def test_flow_pillars_and_plan():
    v = mv.flow_view("day", _period())
    assert _marks(v) == {"Net flow": "up", "Inflow sessions": "up", "Turnover vs average": "up", "Breadth": "up"}
    assert v["verdict"] == "Money flowing in, turnover 59% above average"
    assert [t["pct"] for t in v["plan"]] == [None, None, None]
    assert v["change_view"] == "Net money flowing out, or inflow on 7 or fewer of the last 14 sessions."


def test_inflow_sessions_half_is_flat():
    assert mv._p_inflow_sessions(_flow(inflow_sessions_14=7))["mark"] == "flat"
    assert mv._p_inflow_sessions(_flow(inflow_sessions_14=3))["mark"] == "down"


# ---- sectors -------------------------------------------------------------

def test_sector_pillars_use_display_names():
    v = mv.sectors_view("day", _period())
    assert _marks(v) == {"Leader": "up", "Laggard": "down", "Sectors in X columns": "flat",
                         "Money into the top sector": "up"}
    assert v["pillars"][0]["reading"] == "Services & Real Estate +3.7%"
    assert "Bank, net Tk 87 crore in" in v["pillars"][3]["reading"]
    assert [t["label"] for t in v["plan"]] == ["Services & Real Estate", "Bank"]
    assert v["verdict"] == "3 of 4 sectors up, Services & Real Estate leads"


def test_no_sector_took_in_money():
    rows = [{"sector": s, "chg_pct": c, "bp_column": "O", "net_cr": n} for s, c, n in
            (("Bank", -0.5, -3.0), ("IT", -1.0, -9.0), ("Jute", -2.0, -1.0))]
    v = mv.sectors_view("day", _period(sectors=_sectors(rows)))
    assert v["badge"] == "▼" and "Jute lost the least" in v["pillars"][3]["reading"]


# ---- signals -------------------------------------------------------------

def test_signal_pillars():
    v = mv.signals_view("day", _period())
    assert _marks(v) == {"Buys vs sells": "up", "Beating DSEX": "up", "Volume surge": "up"}
    assert v["verdict"] == "23 buy and 6 sell signals"
    assert [(t["label"], t["value"], t["pct"]) for t in v["plan"]] == [("Buys", 23, None), ("Sells", 6, None)]


def test_beating_share_and_volume_rules():
    few = mv._p_beating(_signals(beating=10), _flow())          # 10 of 383 traded = 3%
    assert few["mark"] == "down" and "3% of 383 traded" in few["reading"]
    assert mv._p_beating(_signals(beating=10), {})["mark"] == "flat"
    assert mv._p_volume(_signals(volume=0), _flow())["mark"] == "flat"
    assert mv._p_volume(_signals(volume=9), _flow(net_cr=-5.0))["mark"] == "down"


def test_volume_ratio_matches_the_signals_module():
    from dsereport import signals
    assert mv.VOLUME_RATIO == signals.VOLUME_RATIO


# ---- the real report -----------------------------------------------------

@pytest.fixture(scope="module")
def report():
    with open(FIXTURE, encoding="utf-8") as f:
        return build.build_report(json.load(f), None, built_at="2026-11-17T11:05:00Z")


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


@pytest.mark.parametrize("p", ["day", "week", "month"])
@pytest.mark.parametrize("card", mv.CARDS)
def test_real_views_are_complete_and_clean(report, p, card):
    v = report["periods"][p]["views"][card]
    assert v is not None and set(v) == set(schema.VIEW_KEYS)
    assert v["badge"] in schema.MARKET_BADGES and len(v["verdict"]) <= mv.MAX_VERDICT
    assert 3 <= len(v["pillars"]) <= 7 and v["sub"].endswith(f"of {len(v['pillars'])} pillars up")
    assert len(re.findall(r"[.!?](?:\s|$)", v["thesis"])) == 2
    for s in _strings(v):
        assert not re.search(r"\b(None|nan|null)\b", s), s
        assert not re.search(r"(FuelPower|ServRealEst|PharmaChem|TravelLeisur)", s), s
    errors = []
    schema.check_view(v, "v", errors)
    assert errors == []


def test_real_report_validates_with_views(report):
    assert schema.validate(report) == []
    assert report["periods"]["day"]["views"]["trend"]["verdict"] == "Recovering, under resistance"
