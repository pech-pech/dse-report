from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsereport import brief

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"
M = "−"


def market(chg_pct=0.61, chg_pts=33.2, close=5480.0, status="BUY", column="X",
           zone="below 50 midline", bp_col="X", bp=34.0):
    return {
        "asof": "2026-11-17", "label": "Tue 17 Nov",
        "dsex": {"close": close, "chg_pts": chg_pts, "chg_pct": chg_pct},
        "pf": {"status": status, "column": column, "pattern": "Double top breakout",
               "signal_date": "2026-11-10", "target": 5700.0, "next_box": 5520.0,
               "reverse_at": 5380.0, "stop": 5300.0},
        "bp": {"value": bp, "column": bp_col, "zone": zone, "signal": "SELL",
               "column_since": "2026-11-16", "reverse_at": 28.0, "start_value": 32.0,
               "path": [30.0, 32.0, bp]},
        "regime": {"name": "Pullback", "note": "DSEX above its EMA200 but its EMA50 falling"},
        "levels": [],
    }


def trend(above_signal=True, above_zero=False, hist_run=3):
    return {
        "headline": "Above two of three averages; EMA200 overhead",
        "sentence": "x",
        "macd_state": {"above_signal": above_signal, "above_zero": above_zero,
                       "hist_run": hist_run, "last_signal_cross": None},
    }


def flow(net=45.0, adv=261, dec=76, unch=78, turnover=812.0, vs=1.12, sessions=1):
    return {
        "sessions": sessions, "adv": adv, "dec": dec, "unch": unch,
        "turnover_cr": turnover, "turnover_avg_cr": turnover / sessions, "vs_avg20": vs,
        "in_cr": 400.0, "out_cr": 400.0 - net, "flat_cr": 12.0, "net_cr": net,
        "last14": [1.0] * 14, "inflow_sessions_14": 9, "by_sector": {"Bank": 20.0},
    }


def sector_rows():
    return [
        {"sector": "Ceramic", "chg_pct": 3.2, "bp": 45.0, "bp_column": "X", "bp_zone": "below 50 midline",
         "net_cr": 5.0, "stocks": 5},
        {"sector": "Bank", "chg_pct": 1.0, "bp": 40.0, "bp_column": "X", "bp_zone": "below 50 midline",
         "net_cr": 20.0, "stocks": 35},
        {"sector": "IT", "chg_pct": -1.4, "bp": 20.0, "bp_column": "O", "bp_zone": "oversold (<30)",
         "net_cr": -8.0, "stocks": 11},
    ]


def sigs(buys=23, sells=6):
    return {"buys": [], "sells": [], "beating": [], "volume": [],
            "counts": {"buys": buys, "sells": sells, "beating": 5, "volume": 7}}


def setups():
    return [{"code": "ABC", "sector": "Bank", "close": 44.0, "trigger": 45.6, "target": 52.0,
             "cancel": 41.0, "score": 6, "conditions": [{}] * 7, "caution": None}]


def records():
    return [{"code": "XYZ", "record_date": "2026-11-24", "label": "Tue 24 Nov", "sessions_away": 5,
             "last_buy": "2026-11-22", "last_buy_label": "Sun 22 Nov", "dividend_text": "105% cash",
             "dividends": [{"kind": "cash", "pct": 105.0, "tk_per_share": 10.5}], "can_still_buy": True}]


def run(p="day", **kw):
    args = dict(market=market(), trend=trend(), flow=flow(), sectors=sector_rows(), sigs=sigs(),
                setups=setups(), records=records())
    args.update(kw)
    return brief.summarize(p, **args)


# ---- verdict -------------------------------------------------------------

def test_verdict_up_with_money_in():
    assert run()["verdict"] == "Up, with money flowing in"


def test_verdict_down_with_money_out():
    out = run(market=market(chg_pct=-0.8, chg_pts=-44.0), flow=flow(net=-30.0))
    assert out["verdict"] == "Down, with money flowing out"


def test_verdict_up_but_money_out_and_down_but_in():
    assert run(flow=flow(net=-3.0))["verdict"] == "Up, but money flowing out"
    assert run(market=market(chg_pct=-0.5), flow=flow(net=3.0))["verdict"] == "Down, but money flowing in"


def test_verdict_turnover_clause_when_net_is_zero():
    assert run(market=market(chg_pct=-0.5), flow=flow(net=0.0, vs=0.6))["verdict"] == "Down on thin turnover"
    assert run(flow=flow(net=0.0, vs=1.5))["verdict"] == "Up on heavy turnover"
    assert run(flow=flow(net=0.0, vs=1.0))["verdict"] == "Up"


def test_verdict_flat_day():
    out = run(market=market(chg_pct=0.02, chg_pts=1.1), flow=flow(net=0.0, vs=1.0))
    assert out["verdict"] == "Flat"
    assert run(market=market(chg_pct=0.0), flow=flow(net=5.0))["verdict"] == "Flat, with money flowing in"


def test_verdict_missing_index():
    out = run(market=None)
    assert out["verdict"] == "No index data"
    assert len(out["verdict"].split()) <= 6


# ---- lede ----------------------------------------------------------------

def test_lede_day_has_three_sentences_from_numbers():
    lede = run()["lede"]
    assert lede.count(". ") == 2 and lede.endswith(".")
    assert "DSEX rose 33.2 points (+0.61%) today to 5,480.0" in lede
    assert "Tk 812 crore" in lede and "12% above its 20-session average" in lede
    assert "net Tk 45 crore in" in lede
    assert "261 stocks rose and 76 fell" in lede
    assert "Ceramic led (+3.2%)" in lede and f"IT lagged ({M}1.4%)" in lede
    assert "23 buy and 6 sell signals" in lede


def test_lede_down_week():
    out = run("week", market=market(chg_pct=-1.2, chg_pts=-66.0),
              flow=flow(net=-120.0, adv=90, dec=300, turnover=3000.0, vs=0.7, sessions=3))
    lede = out["lede"]
    assert "DSEX fell 66.0 points" in lede and "this week" in lede
    assert "Tk 3,000 crore over 3 sessions (Tk 1,000 crore a session)" in lede
    assert "30% below its 20-session average" in lede
    assert "net Tk 120 crore out" in lede
    assert "90 advances and 300 declines over 3 sessions" in lede


def test_lede_flat_and_turnover_in_line():
    lede = run(market=market(chg_pct=0.0, chg_pts=0.0), flow=flow(vs=1.004))["lede"]
    assert "DSEX was unchanged today at 5,480.0" in lede
    assert "in line with its 20-session average" in lede


def test_lede_missing_everything_still_reads():
    out = brief.summarize("day", None, None, None, [], None, [], [])
    assert out["lede"]
    assert "No index data" in out["lede"]
    assert "–" not in out["verdict"]


# ---- glance --------------------------------------------------------------

def test_glance_rows():
    g = run()["glance"]
    labels = [r[0] for r in g]
    assert labels == ["DSEX", "Up / down", "Net money flow Tk cr", "Turnover Tk cr", "Bullish %"]
    assert g[0] == ["DSEX", "5,480.0", "+0.61%"]
    assert g[1] == ["Up / down", "261 / 76", "78 unchanged"]
    assert g[2][1] == "+45"
    assert g[3] == ["Turnover Tk cr", "812", "+12% vs avg"]
    assert g[4] == ["Bullish %", "34.0", "+2.0 pts"]


def test_glance_missing_is_dash():
    g = brief.summarize("day", None, None, None, [], None, [], [])["glance"]
    assert all(r[1] == "–" for r in g)


# ---- answers -------------------------------------------------------------

def answers(out):
    return {a["q"]: a for a in out["answers"]}


def test_eight_answers_with_cards():
    out = run()
    assert len(out["answers"]) == 8
    cards = [a["card"] for a in out["answers"]]
    assert cards == [2, 1, 1, 3, 2, 4, 5, 6]
    for a in out["answers"]:
        assert a["tone"] in ("up", "down", "flat")
        assert a["state"] and a["detail"]


def test_answers_up_day():
    a = answers(run())
    assert a["Is DSEX in an uptrend?"]["state"] == "Yes"
    assert "Double top breakout" in a["Is DSEX in an uptrend?"]["detail"]
    assert a["Are most stocks rising?"]["state"] == "Yes"
    assert a["Is it oversold?"]["state"] == "No"
    assert "34.0" in a["Is it oversold?"]["detail"]
    assert a["Where is money going?"]["state"] == "Bank"
    assert "Tk 20 crore" in a["Where is money going?"]["detail"]
    assert a["Is momentum building?"]["state"] == "Yes"
    assert "rising 3 sessions" in a["Is momentum building?"]["detail"]
    assert a["Which sector leads?"]["state"] == "Ceramic"
    assert a["What signalled?"]["state"] == "23 buys · 6 sells"
    assert a["What signalled?"]["tone"] == "up"
    assert a["What may break out?"]["state"] == "1 setup"
    assert "ABC" in a["What may break out?"]["detail"]


def test_answers_down_day():
    rows = [dict(r, net_cr=-abs(r["net_cr"]) - 1) for r in sector_rows()]
    a = answers(run(market=market(status="SELL", column="O", zone="oversold (<30)", bp_col="O", bp=22.0),
                    trend=trend(above_signal=False, hist_run=-4), flow=flow(net=-50.0, adv=50, dec=300),
                    sectors=rows, sigs=sigs(buys=2, sells=19), setups=[]))
    assert a["Is DSEX in an uptrend?"]["state"] == "No"
    assert a["Is DSEX in an uptrend?"]["tone"] == "down"
    assert a["Are most stocks rising?"]["state"] == "No"
    assert a["Is it oversold?"]["state"] == "Yes"
    assert a["Where is money going?"]["state"] == "Out of every sector"
    assert a["Where is money going?"]["tone"] == "down"
    assert a["Is momentum building?"]["state"] == "No"
    assert "falling 4 sessions" in a["Is momentum building?"]["detail"]
    assert a["What signalled?"]["tone"] == "down"
    assert a["What may break out?"]["state"] == "None"
    assert a["What may break out?"]["card"] is None


def test_answers_mixed_states():
    a = answers(run(market=market(status="BUY", column="O", zone="overbought (>70)", bp=75.0),
                    trend=trend(above_signal=True, hist_run=-1), flow=flow(adv=100, dec=100),
                    sigs=sigs(buys=4, sells=4)))
    assert a["Is DSEX in an uptrend?"]["state"] == "Buy signal, pulling back"
    assert a["Is it oversold?"]["state"] == "No, overbought"
    assert a["Are most stocks rising?"]["state"] == "Evenly split"
    assert a["Is momentum building?"]["state"] == "Mixed"
    assert a["What signalled?"]["tone"] == "flat"
    b = answers(run(market=market(status="SELL", column="X")))
    assert b["Is DSEX in an uptrend?"]["state"] == "Sell signal, bouncing"


def test_answers_money_from_flow_by_sector_when_rows_missing():
    a = answers(run(sectors=[]))
    assert a["Where is money going?"]["state"] == "Bank"
    assert a["Which sector leads?"]["state"] == "No data"


def test_answers_missing_data():
    out = brief.summarize("day", None, None, None, [], None, [], [])
    assert len(out["answers"]) == 8
    for a in out["answers"]:
        assert a["tone"] == "flat"
    assert answers(out)["Is DSEX in an uptrend?"]["state"] == "No data"


# ---- notification --------------------------------------------------------

def test_notification():
    n = run()["notification"]
    assert n["title"] == "DSEX +0.61% · 23 buys · 6 sells"
    assert len(n["lines"]) == 5
    assert n["lines"][0] == "Turnover Tk 812 crore, +12% vs average"
    assert "XYZ" in n["lines"][-1] and "Sun 22 Nov" in n["lines"][-1]


def test_notification_down_and_missing():
    n = run(market=market(chg_pct=-0.8), records=[])["notification"]
    assert n["title"].startswith(f"DSEX {M}0.80%")
    assert "ABC" in n["lines"][-1]
    empty = brief.summarize("day", None, None, None, [], None, [], [])["notification"]
    assert empty["title"] == "DSEX – · 0 buys · 0 sells"


def test_unknown_period_rejected():
    with pytest.raises(ValueError):
        run("year")


def test_inputs_not_mutated_and_json_safe():
    m, f, rows = market(), flow(), sector_rows()
    snap = json.dumps([m, f, rows])
    out = run(market=m, flow=f, sectors=rows)
    assert json.dumps([m, f, rows]) == snap
    json.dumps(out, allow_nan=False)


# ---- real fixture --------------------------------------------------------

def _from_fixture(I):
    """Contract-shaped stand-ins for the other modules' outputs, built from the real inputs."""
    d = I["dsex"]
    close = d["close"]
    bt, mb = I["breadth_today"], I["market_bp"]
    m = {"dsex": {"close": close[-1], "chg_pts": close[-1] - close[-2],
                  "chg_pct": (close[-1] / close[-2] - 1) * 100},
         "pf": {"status": d["status"], "column": d["action_points"]["column"],
                "pattern": d["last_signal"]["pattern"], "signal_date": d["last_signal"]["date"],
                "next_box": d["action_points"]["next"], "reverse_at": d["action_points"]["reverse"]},
         "bp": {"value": mb["bp"], "column": mb["column"], "zone": mb["zone"],
                "column_since": mb["column_since"], "reverse_at": mb["reverse_at"],
                "start_value": I["bp_series"][-2][1]}}
    f = {"sessions": 1, "adv": bt["advancers"], "dec": bt["decliners"],
         "unch": bt["stocks"] - bt["advancers"] - bt["decliners"], "turnover_cr": 800.0,
         "turnover_avg_cr": 800.0, "vs_avg20": 1.0, "net_cr": 10.0, "inflow_sessions_14": 7,
         "by_sector": {}}
    rows = sorted(({"sector": r["sector"], "chg_pct": r["chg1d"], "bp": r["bp"],
                    "bp_column": r["bp_column"], "net_cr": 0.0} for r in I["home_sectors"]),
                  key=lambda r: -r["chg_pct"])
    s = {"counts": {"buys": bt["new_buys"], "sells": bt["new_sells"], "beating": 0, "volume": 0}}
    return m, f, rows, s


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture missing")
def test_real_fixture_shape():
    I = json.loads(FIXTURE.read_text())
    m, f, rows, s = _from_fixture(I)
    out = brief.summarize("day", m, None, f, rows, s, [], [])
    assert set(out) == {"verdict", "lede", "glance", "answers", "notification"}
    assert len(out["verdict"].split()) <= 6
    assert len(out["answers"]) == 8 and len(out["glance"]) == 5
    assert out["notification"]["title"].endswith(f"{bt_count(I)}")
    json.dumps(out, allow_nan=False)


def bt_count(I):
    return f"{I['breadth_today']['new_sells']} sells"


def test_multi_session_breadth_says_advances_and_declines():
    from dsereport import brief
    words = brief._breadth_words({"adv": 2278, "dec": 2228, "sessions": 13})
    assert words == "2,278 advances and 2,228 declines over 13 sessions"
    assert brief._breadth_words({"adv": 262, "dec": 77, "sessions": 1}) == "262 stocks rose and 77 fell"


def test_buy_signal_under_a_bear_trend_line_is_not_called_an_uptrend():
    from dsereport import brief
    mkt = {"pf": {"status": "BUY", "column": "X", "trend": "bear", "trend_level": 5688.0, "signal_date": "2026-11-17",
                  "pattern": "Bullish Signal (Diagonal Triple Top)", "next_box": 5504.0, "reverse_at": 5472.0}}
    a = brief._a_uptrend(mkt)
    assert a["state"] == "Buy signal, under the trend line" and a["tone"] == "flat"
    assert "bearish resistance line is at 5,688" in a["detail"]


def test_notification_skips_record_dates_too_late_to_buy_or_without_a_dividend():
    from dsereport import brief
    recs = [{"code": "ACMELAB", "record_date": "2026-11-18", "label": "Wed 18 Nov", "can_still_buy": False, "dividends": [{"kind": "cash", "pct": 40}], "dividend_text": "40% cash", "last_buy_label": "Mon 16 Nov"},
            {"code": "ICB", "record_date": "2026-11-23", "label": "Mon 23 Nov", "can_still_buy": True, "dividends": [], "dividend_text": "No dividend", "last_buy_label": "Wed 18 Nov"},
            {"code": "INTECH", "record_date": "2026-12-06", "label": "Sun 6 Dec", "can_still_buy": True, "dividends": [{"kind": "cash", "pct": 10}], "dividend_text": "10% cash", "last_buy_label": "Wed 2 Dec"}]
    assert brief._closing_line(None, [], [], recs) == "INTECH record date Sun 6 Dec (10% cash), buy by Wed 2 Dec"
    assert brief._closing_line(None, [], [{"code": "GP", "trigger": 292.0}], recs[:2]) == "GP one box from a buy at 292.0"
