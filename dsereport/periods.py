"""Report periods over DSE sessions (the exchange trades Sunday to Thursday)."""
from __future__ import annotations

from datetime import date, timedelta

PERIODS = ("day", "week", "month")


def _d(s: str) -> date:
    return date.fromisoformat(s)


def window(sessions: list[str], period: str) -> list[str]:
    """Sessions in the period ending at the last session: the day; the week from its Sunday; the calendar month."""
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}")
    if not sessions:
        return []
    last = _d(sessions[-1])
    if period == "day":
        return [sessions[-1]]
    if period == "week":
        start = last - timedelta(days=(last.weekday() + 1) % 7)   # back to Sunday
    else:
        start = last.replace(day=1)
    return [s for s in sessions if _d(s) >= start]


def base_session(sessions: list[str], period: str) -> str | None:
    """The session before the period starts: the close every period change is measured from."""
    w = window(sessions, period)
    if not w:
        return None
    i = sessions.index(w[0])
    return sessions[i - 1] if i > 0 else None


def label(sessions: list[str], period: str) -> str:
    """'Tue 17 Nov', '15–17 Nov' or '1–17 Nov'."""
    w = window(sessions, period)
    if not w:
        return ""
    a, b = _d(w[0]), _d(w[-1])
    if period == "day" or a == b:
        return f"{b:%a} {b.day} {b:%b}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {b:%b}"
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def future_sessions(after: str, count: int, holidays: frozenset[str] = frozenset()) -> list[str]:
    """The next ``count`` trading days after ``after`` assuming a Sunday–Thursday week (holidays unknown ahead)."""
    out, d = [], _d(after)
    while len(out) < count:
        d += timedelta(days=1)
        if d.weekday() not in (4, 5) and d.isoformat() not in holidays:   # Friday, Saturday
            out.append(d.isoformat())
    return out
