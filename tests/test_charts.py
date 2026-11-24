"""The chart screen's per-stock files: which codes get one, their shape, the reading, and the checks."""
import json
import math

from dsereport import charts


def _page():
    # an engine-shaped page: levels for boxes 10..19, an X column with a month mark, an O column, one trend line
    return {"levels": [100 + 2 * k for k in range(10)], "b0": 10,
            "cols": [["X", 11, 15, {"13": "A"}, "2026-10-01", "2026-10-20"],
                     ["O", 12, 14, {}, "2026-10-21", "2026-11-17"]],
            "trendlines": [{"kind": "bull", "anchor": 0, "base": 10, "end": 2}], "price_box": 14}


def _inputs(n=5):
    closes = [100.0 + i for i in range(n)]
    stock = {"code": "AAA", "sector": "Pharma", "close": closes, "chg": 1.234, "signal": "BUY", "pattern": "Double top",
             "signal_date": "2026-11-17", "column": "X", "target": 120.0, "stop": 95.0, "sell_at": 98.0, "buy_at": None,
             "rs_column": "X", "vol_ratio": 2.44}
    chart = {"pf": _page(), "dates": [f"2026-11-{10 + i}" for i in range(n)], "close": closes,
             "rsi": [None] + [55.0 + i for i in range(n - 1)], "macd": [0.5] * n, "macd_signal": [0.2] * n,
             "macd_hist": [0.3] * n}
    return {"asof": "2026-11-17", "stocks": {"AAA": stock, "BBB": dict(stock, code="BBB")}, "charts": {"AAA": chart}}


REPORT = {"periods": {"day": {"signals": {"buys": [{"code": "AAA"}, {"code": "ZZZ"}]}}},
          "setups": [{"code": "BBB", "title": "BBB: one box"}], "records": []}


def test_codes_in_finds_every_named_stock_and_ignores_unknown_codes():
    assert charts.codes_in(REPORT, _inputs()["stocks"]) == ["AAA", "BBB"]


def test_build_charts_skips_codes_without_chart_inputs():
    out = charts.build_charts(_inputs(), REPORT)
    assert list(out) == ["AAA"]


def test_stock_chart_shape_and_header():
    c = charts.stock_chart(_inputs(), "AAA")
    assert c["schema"] == charts.CHART_SCHEMA and c["asOf"] == "2026-11-17" and c["sector"] == "Pharma"
    h = c["header"]
    assert h["close"] == 104.0 and h["chg"] == 1.23 and h["rvol"] == 2.4
    assert h["reverse_at"] == 98.0          # on a buy, the reversal is the sell price
    assert c["pf"]["cols"][0][3] == {"13": "A"}
    assert c["series"]["rsi"][0] is None and len(c["series"]["dates"]) == 5


def test_reverse_at_is_the_buy_price_on_a_sell():
    I = _inputs()
    I["stocks"]["AAA"].update(signal="SELL", buy_at=110.0)
    assert charts.stock_chart(I, "AAA")["header"]["reverse_at"] == 110.0


def test_reading_is_plain_and_uses_the_numbers():
    r = charts.stock_chart(_inputs(), "AAA")["reading"]
    assert r.startswith("On a P&F buy since")
    assert "target is 15% above the close" in r
    assert "RSI 58 is between 30 and 70" in r
    assert "MACD is above its signal line and above zero" in r
    assert not any(w in r.lower() for w in ("should", "recommend", "buy now", "sell now"))


def test_reading_extremes_and_missing_data():
    I = _inputs()
    I["charts"]["AAA"]["rsi"] = [75.0] * 5
    I["charts"]["AAA"]["macd"] = [-1.0] * 5
    r = charts.stock_chart(I, "AAA")["reading"]
    assert "above 70" in r and "below its signal line and below zero" in r
    I["stocks"]["AAA"]["signal"] = None
    I["charts"]["AAA"].update(rsi=[], macd=[], macd_signal=[])
    assert charts.stock_chart(I, "AAA")["reading"] == "Not enough history for a reading yet."


def test_missing_stock_or_chart_gives_none():
    assert charts.stock_chart(_inputs(), "BBB") is None
    assert charts.stock_chart(_inputs(), "NOPE") is None


def test_nan_values_become_none_and_the_file_is_json():
    I = _inputs()
    I["charts"]["AAA"]["macd"][2] = math.nan
    c = charts.stock_chart(I, "AAA")
    assert c["series"]["macd"][2] is None
    json.loads(json.dumps(c, allow_nan=False))


def test_validate_accepts_a_good_chart():
    assert charts.validate_chart(charts.stock_chart(_inputs(), "AAA")) == []


def test_validate_accepts_a_chart_without_pf():
    I = _inputs()
    I["charts"]["AAA"]["pf"] = None
    assert charts.validate_chart(charts.stock_chart(I, "AAA")) == []


def test_validate_catches_bad_shapes():
    c = charts.stock_chart(_inputs(), "AAA")
    c["series"]["rsi"] = c["series"]["rsi"][:3]
    c["pf"]["cols"].append(["X", 5, 30, {}, None, None])
    c["pf"]["cols"].append(["Z", 11, 12, {}, None, None])
    c["pf"]["cols"].append(["X", 11, 12, {"11": "Sep"}, None, None])
    c["pf"]["trendlines"].append({"kind": "up"})
    c["reading"] = math.inf
    errs = " | ".join(charts.validate_chart(c))
    for bit in ("different lengths", "boxes outside", "expected [d, lo, hi", "month mark too long", "unknown kind",
                "not a finite number"):
        assert bit in errs
    assert charts.validate_chart({"code": "X"}) == ["chart: missing keys"]
