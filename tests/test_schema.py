import copy

from dsereport import schema


def _period():
    return {"label": "Tue 17 Nov", "sessions": 1, "market": {}, "trend": {}, "flow": {}, "sectors": {}, "news": [], "papers": [],
            "summary": {"verdict": "Up", "lede": "DSEX rose.", "glance": [], "answers": [{}] * 8, "notification": {}},
            "signals": {"buys": [], "sells": [], "beating": [], "volume": [], "counts": {}},
            "views": {c: None for c in schema.MARKET_CARDS}}


def good():
    return {"schema": 1, "asOf": "2026-11-17", "builtAt": "2026-11-17T10:55:00Z", "setups": [], "records": [], "notification": {},
            "periods": {p: _period() for p in ("day", "week", "month")}}


def test_a_complete_report_passes():
    assert schema.validate(good()) == []


def test_missing_top_level_keys_are_named():
    r = good()
    del r["setups"]
    assert schema.validate(r) == ["report: missing setups"]


def test_not_an_object():
    assert schema.validate([]) == ["report: expected an object"]


def test_wrong_version_and_missing_period():
    r = good()
    r["schema"] = 2
    del r["periods"]["week"]
    errs = schema.validate(r)
    assert "report.schema: expected 1" in errs and "periods: missing week" in errs


def test_period_problems():
    r = good()
    r["periods"]["day"]["summary"]["answers"] = [{}] * 7
    r["periods"]["day"]["summary"]["lede"] = " "
    r["periods"]["day"]["signals"]["buys"] = [{}] * 6
    errs = schema.validate(r)
    assert any("answers: expected 8" in e for e in errs)
    assert any("lede: empty" in e for e in errs)
    assert any("buys: more than 5" in e for e in errs)


def test_missing_period_and_summary_keys():
    r = good()
    del r["periods"]["day"]["trend"]
    r2 = good()
    del r2["periods"]["month"]["summary"]["verdict"]
    r2["periods"]["month"]["signals"] = "x"
    assert any("periods.day: missing trend" in e for e in schema.validate(r))
    errs = schema.validate(r2)
    assert any("summary: missing verdict" in e for e in errs) and any("signals: expected an object" in e for e in errs)


def test_nan_and_odd_types_are_rejected():
    r = good()
    r["periods"]["day"]["market"] = {"x": float("nan"), "y": {1, 2}, 3: "k"}
    errs = schema.validate(r)
    assert any("not a finite number" in e for e in errs)
    assert any("unsupported type set" in e for e in errs)
    assert any("non-string key" in e for e in errs)
    assert copy.deepcopy(good()) == good()


def _view():
    return {"badge": "▲", "tone": "up", "verdict": "Broad advance, money flowing in", "sub": "3 of 3 pillars up",
            "thesis": "DSEX rose. We would watch 5,472.", "plan_note": None, "change_view": "A box at 5,472.",
            "method": "Rules-based.", "plan": [{"label": "DSEX close", "value": 5496.7, "pct": None, "tone": "acc"}],
            "pillars": [{"name": n, "mark": "up", "reading": "262 up"} for n in ("A", "B", "C")]}


def test_a_market_view_passes():
    r = good()
    r["periods"]["day"]["views"]["summary"] = _view()
    assert schema.validate(r) == []


def test_market_view_problems_are_named():
    r = good()
    v = _view()
    v.update(badge="A", verdict="x" * 49, thesis="Close at None.", pillars=v["pillars"][:2])
    v["plan"][0]["tone"] = "warn"
    r["periods"]["day"]["views"]["trend"] = v
    del r["periods"]["week"]["views"]["flow"]
    errs = schema.validate(r)
    for want in ("trend.badge", "verdict: longer than 48", "thesis: contains None", "at least 3 pillars",
                 "plan[0].tone", "week.views: missing flow"):
        assert any(want in e for e in errs), want
