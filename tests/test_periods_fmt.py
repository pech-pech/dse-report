import pytest

from dsereport import fmt, periods

SESSIONS = ["2026-10-28", "2026-10-29", "2026-11-01", "2026-11-02", "2026-11-12", "2026-11-15", "2026-11-16", "2026-11-17"]


def test_day_window_is_the_last_session():
    assert periods.window(SESSIONS, "day") == ["2026-11-17"]


def test_week_window_starts_on_sunday():
    assert periods.window(SESSIONS, "week") == ["2026-11-15", "2026-11-16", "2026-11-17"]


def test_month_window_is_the_calendar_month():
    assert periods.window(SESSIONS, "month")[0] == "2026-11-01"
    assert len(periods.window(SESSIONS, "month")) == 6


def test_base_session_is_the_close_before_the_period():
    assert periods.base_session(SESSIONS, "day") == "2026-11-16"
    assert periods.base_session(SESSIONS, "week") == "2026-11-12"
    assert periods.base_session(SESSIONS, "month") == "2026-10-29"


def test_base_session_none_when_period_starts_the_history():
    assert periods.base_session(["2026-11-17"], "day") is None


def test_unknown_period_and_empty_sessions():
    with pytest.raises(ValueError):
        periods.window(SESSIONS, "year")
    assert periods.window([], "day") == [] and periods.label([], "day") == "" and periods.base_session([], "day") is None


def test_labels():
    assert periods.label(SESSIONS, "day") == "Tue 17 Nov"
    assert periods.label(SESSIONS, "week") == "15–17 Nov"
    assert periods.label(["2026-11-29", "2026-12-01"], "week") == "29 Nov–1 Dec"
    assert periods.label(["2026-10-29", "2026-11-01"], "week") == "Sun 1 Nov"


def test_future_sessions_skip_friday_and_saturday():
    assert periods.future_sessions("2026-11-19", 2) == ["2026-11-22", "2026-11-23"]
    assert periods.future_sessions("2026-11-17", 1, frozenset({"2026-11-18"})) == ["2026-11-19"]


@pytest.mark.parametrize("v,d,out", [(1862400, 0, "18,62,400"), (812.44, 1, "812.4"), (-41.25, 1, "−41.2"), (None, 1, "–"), (0, 2, "0.00"), (999, 0, "999")])
def test_num(v, d, out):
    assert fmt.num(v, d) == out


def test_signed_pct_tone_day():
    assert fmt.signed(41.2) == "+41.2" and fmt.signed(-0.04) == "0.0" and fmt.signed(None) == "–"
    assert fmt.pct(0.736, 2) == "+0.74%" and fmt.pct(None) == "–"
    assert (fmt.tone(1), fmt.tone(-1), fmt.tone(0), fmt.tone(None)) == ("up", "down", "flat", "flat")
    assert fmt.day("2026-11-22") == "Sun 22 Nov"
