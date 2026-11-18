from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsereport import events as ev

FIXTURE = Path(__file__).parent / "fixtures" / "inputs_2026-11-17.json"
SESSIONS = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]


def _row(code, kind, date, announced, value=None, detail="", title="Dividend Declaration"):
    return {"code": code, "kind": kind, "date": date, "announced": announced, "value": value,
            "detail": detail, "title": title}


def _inputs(events, stocks=None, daily=None):
    return {"asof": "2026-11-17", "sessions": list(SESSIONS), "events": events,
            "stocks": stocks or {}, "daily": daily or []}


def _stock(code, closes, dates, category="A"):
    return {"code": code, "category": category, "dates": dates, "close": closes}


DECL = "2026-11-10"
ACME_ROWS = [
    _row("ACME", "agm", "2026-12-10", DECL, detail="AGM"),
    _row("ACME", "cash_dividend", DECL, DECL, 25.0, "25% cash, year/period ended 2026-06-30"),
    _row("ACME", "stock_dividend", DECL, DECL, 5.0, "5% stock, year/period ended 2026-06-30"),
    _row("ACME", "earnings", DECL, DECL, 3.5, "annual results for year/period ended 2026-06-30: EPS Tk 3.50"),
    _row("ACME", "record_date", "2026-11-24", DECL, detail="record date (Dividend Declaration)"),
]


# ---------- record_dates ----------

def test_record_date_with_cash_and_stock_dividend():
    stocks = {"ACME": _stock("ACME", [40.0, 50.0], ["2026-11-10", "2026-11-17"], "A")}
    out = ev.record_dates(_inputs(ACME_ROWS, stocks))
    assert len(out) == 1
    r = out[0]
    assert r["code"] == "ACME" and r["record_date"] == "2026-11-24"
    assert r["label"] == "Tue 24 Nov"
    # future sessions: 18 Wed, 19 Thu, 22 Sun, 23 Mon, 24 Tue
    assert r["sessions_away"] == 5
    assert r["last_buy"] == "2026-11-22" and r["last_buy_label"] == "Sun 22 Nov"
    assert r["can_still_buy"] is True
    assert r["dividends"] == [{"kind": "cash", "pct": 25.0, "tk_per_share": 2.5},
                              {"kind": "stock", "pct": 5.0, "tk_per_share": None}]
    assert r["dividend_text"] == "25% cash + 5% stock"
    assert r["declared_on"] == DECL
    assert r["close"] == 50.0
    assert r["cash_yield_pct"] == 5.0
    assert r["since_declared_pct"] == 25.0
    assert r["category"] == "A"


def test_record_date_on_friday_uses_sessions_before_it():
    rows = [_row("X", "record_date", "2026-11-20", DECL, detail="record date (Dividend Declaration)")]
    r = ev.record_dates(_inputs(rows))[0]
    assert r["sessions_away"] == 2          # Wed 18, Thu 19
    assert r["last_buy"] == "2026-11-17"    # T+2 = Thu 19 <= Fri 20; today, so too late after the close
    assert r["can_still_buy"] is False
    assert r["close"] is None and r["cash_yield_pct"] is None and r["since_declared_pct"] is None


def test_record_date_tomorrow_buy_window_passed():
    rows = [_row("X", "record_date", "2026-11-18", DECL, detail="record date (Dividend Declaration)")]
    r = ev.record_dates(_inputs(rows))[0]
    assert r["sessions_away"] == 1
    assert r["last_buy"] == "2026-11-16"
    assert r["can_still_buy"] is False


def test_record_dates_exclude_past_and_sort_and_limit():
    rows = [_row(c, "record_date", d, DECL, detail="record date (Dividend Declaration)")
            for c, d in [("PAST", "2026-11-17"), ("B", "2026-12-01"), ("A", "2026-11-19"), ("C", "2026-11-25")]]
    out = ev.record_dates(_inputs(rows), limit=2)
    assert [r["code"] for r in out] == ["C", "B"]           # buyable first; A's last day to buy has passed
    assert [r["code"] for r in ev.record_dates(_inputs(rows))] == ["C", "B", "A"]


def test_no_dividend_and_unknown_dividend_texts():
    rows = [
        _row("Z", "cash_dividend", DECL, DECL, 0.0, "no dividend, year/period ended 2026-06-30"),
        _row("Z", "record_date", "2026-11-26", DECL, detail="record date (Dividend Declaration)"),
        _row("F", "record_date", "2026-11-26", "2026-11-01", detail="record date (Spot News)", title="Spot News"),
    ]
    out = {r["code"]: r for r in ev.record_dates(_inputs(rows))}
    assert out["Z"]["dividend_text"] == "No dividend" and out["Z"]["dividends"] == []
    assert out["Z"]["cash_yield_pct"] is None
    assert out["F"]["dividend_text"] == "Dividend not in the news yet"


def test_tk_per_share_cash_and_daily_close_fallback():
    rows = [
        _row("K", "cash_dividend", DECL, DECL, None, "Tk 2.00 per share/unit cash, year/period ended 2026-06-30"),
        _row("K", "record_date", "2026-11-26", DECL, detail="record date (Dividend Declaration)"),
    ]
    daily = [["K", "2026-11-10", 18.0, 17.0, 100], ["K", "2026-11-17", 20.0, 19.0, 100]]
    r = ev.record_dates(_inputs(rows, daily=daily))[0]
    assert r["dividends"] == [{"kind": "cash", "pct": 20.0, "tk_per_share": 2.0}]
    assert r["dividend_text"] == "20% cash"
    assert r["close"] == 20.0 and r["cash_yield_pct"] == 10.0
    assert r["since_declared_pct"] == pytest.approx(11.11, abs=0.01)
    assert r["category"] is None


def test_record_dates_does_not_mutate_inputs():
    I = _inputs(ACME_ROWS)
    before = json.dumps(I, sort_keys=True)
    ev.record_dates(I)
    ev.company_news(I, "week")
    assert json.dumps(I, sort_keys=True) == before


# ---------- sentences ----------

@pytest.mark.parametrize("detail,value,text", [
    ("annual results for year/period ended 2026-06-30: EPS Tk (0.33)", -0.33,
     "Annual EPS Tk −0.33 (year to 30 Jun 2026)"),
    ("Q3 results: EPS Tk 0.76; cumulative EPS Tk 1.79", 0.76, "Q3 EPS Tk 0.76 (cumulative Tk 1.79)"),
    ("Q1 results: EPS Tk (0.12)", -0.12, "Q1 EPS Tk −0.12"),
    ("Q2 results: EPS Tk (0.20); cumulative EPS Tk (0.50)", -0.2, "Q2 EPS Tk −0.20 (cumulative Tk −0.50)"),
    ("Q3 results (EPS not parsed)", None, "Q3 results published"),
])
def test_earnings_sentences(detail, value, text):
    assert ev.event_text(_row("X", "earnings", DECL, DECL, value, detail)) == text


@pytest.mark.parametrize("kind,detail,value,text", [
    ("cash_dividend", "no dividend, year/period ended 2026-06-30", 0.0, "No dividend for the year to 30 Jun 2026"),
    ("cash_dividend", "20% cash, year/period ended 2026-06-30", 20.0, "20% cash dividend (year to 30 Jun 2026)"),
    ("cash_dividend", "350% cash (interim)", 350.0, "350% interim cash dividend"),
    ("cash_dividend", "10% final cash, year/period ended 2026-06-30", 10.0,
     "10% final cash dividend (year to 30 Jun 2026)"),
    ("cash_dividend", "5% cash (excl. sponsors/directors), year/period ended 2026-06-30", 5.0,
     "5% cash dividend, sponsors/directors excluded (year to 30 Jun 2026)"),
    ("stock_dividend", "8% stock, year/period ended 2026-06-30", 8.0, "8% stock dividend (year to 30 Jun 2026)"),
    ("cash_dividend", "Tk 1.00 per share/unit cash, year/period ended 2026-06-30", None,
     "Tk 1.00 a share cash dividend (year to 30 Jun 2026)"),
    ("category", "Z -> A", None, "Moves from Z to A category"),
    ("record_date", "record date (Dividend Declaration)", None, "Record date Thu 26 Nov"),
    ("record_date", "record date (Spot News)", None, "Record date Thu 26 Nov (Spot News)"),
    ("agm", "AGM", None, "AGM Thu 26 Nov"),
    ("agm", "EGM", None, "EGM Thu 26 Nov"),
])
def test_other_sentences(kind, detail, value, text):
    assert ev.event_text(_row("X", kind, "2026-11-26", DECL, value, detail)) == text


def test_unknown_wording_falls_back_to_title():
    row = _row("X", "earnings", DECL, DECL, None, "something new", title="Price Sensitive Information")
    assert ev.event_text(row) == "Price Sensitive Information"
    row = _row("X", "weird", DECL, DECL, None, "??", title="Odd Notice")
    assert ev.event_text(row) == "Odd Notice"


# ---------- company_news ----------

def test_company_news_merges_rows_and_measures_move():
    rows = ACME_ROWS + [
        _row("ZED", "category", "2026-11-18", "2026-11-17", detail="Z -> A", title="Category Change"),
        _row("OLD", "category", "2026-11-01", "2026-11-01", detail="B -> Z", title="Category Change"),
        _row("Q", "earnings", "2026-11-16", "2026-11-16", 0.5, "Q1 results: EPS Tk 0.50", title="Q1 Financials"),
    ]
    daily = [["ACME", DECL, 44.0, 40.0, 1], ["ZED", "2026-11-17", 9.5, 10.0, 1]]
    out = ev.company_news(_inputs(rows, daily=daily), "month")
    assert [n["code"] for n in out] == ["ZED", "Q", "ACME"]
    zed, q, acme = out
    assert zed == {"date": "2026-11-17", "code": "ZED", "kind": "Category",
                   "text": "Moves from Z to A category", "move_pct": -5.0}
    assert q["kind"] == "Results" and q["move_pct"] is None
    assert acme["kind"] == "Dividend"
    assert acme["text"] == ("Annual EPS Tk 3.50 (year to 30 Jun 2026); 25% cash dividend; 5% stock dividend; "
                            "record date Tue 24 Nov; AGM Thu 10 Dec")
    assert acme["move_pct"] == 10.0


def test_company_news_period_window_and_limit():
    rows = [_row("A", "category", "2026-11-17", "2026-11-17", detail="B -> Z", title="Category Change"),
            _row("B", "category", "2026-11-14", "2026-11-14", detail="B -> Z", title="Category Change"),
            _row("C", "category", "2026-11-12", "2026-11-12", detail="B -> Z", title="Category Change")]
    I = _inputs(rows)
    assert [n["code"] for n in ev.company_news(I, "day")] == ["A"]
    # week runs from Sunday 15 Nov; base session is Thu 12 Nov, so Sat 14 Nov counts
    assert [n["code"] for n in ev.company_news(I, "week")] == ["A", "B"]
    assert len(ev.company_news(I, "month", limit=2)) == 2


def test_merged_results_annual_first_then_quarters():
    rows = [_row("M", "earnings", DECL, DECL, -0.55, "Q3 results: EPS Tk (0.55)"),
            _row("M", "earnings", DECL, DECL, -0.89, "Q1 results: EPS Tk (0.89)"),
            _row("M", "earnings", DECL, DECL, -2.6, "annual results for year/period ended 2026-06-30: EPS Tk (2.60)"),
            _row("M", "cash_dividend", DECL, DECL, 0.0, "no dividend, year/period ended 2026-06-30")]
    assert ev.merged_text(rows) == ("Annual EPS Tk −2.60 (year to 30 Jun 2026); Q1 EPS Tk −0.89; "
                                    "Q3 EPS Tk −0.55; no dividend")


def test_record_date_kind_label_alone():
    rows = [_row("R", "record_date", "2026-11-30", "2026-11-17", detail="record date (Spot News)", title="Spot News")]
    n = ev.company_news(_inputs(rows), "day")[0]
    assert n["kind"] == "Record date" and n["text"] == "Record date Mon 30 Nov (Spot News)"


# ---------- real fixture ----------

@pytest.fixture(scope="module")
def real():
    return json.loads(FIXTURE.read_text())


def test_real_fixture_record_dates(real):
    out = ev.record_dates(real)
    assert 1 <= len(out) <= 10
    buy = [r["record_date"] for r in out if r["can_still_buy"]]
    late = [r["record_date"] for r in out if not r["can_still_buy"]]
    assert [r["can_still_buy"] for r in out] == sorted((r["can_still_buy"] for r in out), reverse=True)
    assert buy == sorted(buy) and late == sorted(late) and len(late) <= ev.TOO_LATE_SHOWN
    assert all(r["record_date"] > real["asof"] for r in out)
    for r in out:
        assert r["last_buy"] < r["record_date"] and r["sessions_away"] >= 1
        assert isinstance(r["dividend_text"], str) and r["dividend_text"]
    json.dumps(out, allow_nan=False)


def test_real_fixture_company_news(real):
    for p in ("day", "week", "month"):
        out = ev.company_news(real, p)
        assert len(out) <= 12
        assert [n["date"] for n in out] == sorted((n["date"] for n in out), reverse=True)
        assert len({(n["code"], n["date"]) for n in out}) == len(out)
        for n in out:
            assert n["text"] and n["kind"] in ev.LABELS
        json.dumps(out, allow_nan=False)
    assert ev.company_news(real, "month")


def test_spot_news_record_date_pairs_with_earlier_declaration():
    rows = [
        _row("ACME", "cash_dividend", "2026-10-27", "2026-10-27", 40.0, "40% cash, year/period ended 2026-06-30"),
        _row("ACME", "record_date", "2026-11-24", "2026-11-15", detail="record date (Spot News)", title="Spot News"),
    ]
    r = ev.record_dates(_inputs(rows))[0]
    assert r["dividend_text"] == "40% cash" and r["declared_on"] == "2026-10-27"
    assert r["dividends"] == [{"kind": "cash", "pct": 40.0, "tk_per_share": 4.0}]


def test_only_the_latest_declaration_in_the_lookback_counts():
    rows = [
        _row("ACME", "cash_dividend", "2026-03-01", "2026-03-01", 10.0, "10% cash, year/period ended 2025-12-31"),
        _row("ACME", "cash_dividend", "2026-10-27", "2026-10-27", 0.0, "no dividend, year/period ended 2026-06-30"),
        _row("ACME", "record_date", "2026-11-24", "2026-11-15", detail="record date (Spot News)", title="Spot News"),
        _row("OLD", "cash_dividend", "2026-01-02", "2026-01-02", 30.0, "30% cash, year/period ended 2025-09-30"),
        _row("OLD", "record_date", "2026-11-24", "2026-11-15", detail="record date (Spot News)", title="Spot News"),
    ]
    out = {r["code"]: r for r in ev.record_dates(_inputs(rows))}
    assert out["ACME"]["dividend_text"] == "No dividend" and out["ACME"]["declared_on"] == "2026-10-27"
    assert out["OLD"]["dividend_text"] == "Dividend not in the news yet"      # older than the lookback
    assert out["OLD"]["declared_on"] == "2026-11-15"


def test_too_late_record_dates_are_capped():
    rows = [_row(f"L{i}", "record_date", "2026-11-18", DECL, detail="record date") for i in range(6)]
    rows.append(_row("OK", "record_date", "2026-11-30", DECL, detail="record date"))
    out = ev.record_dates(_inputs(rows))
    assert out[0]["code"] == "OK" and len(out) == 1 + ev.TOO_LATE_SHOWN
