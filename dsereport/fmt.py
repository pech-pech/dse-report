"""Number and date wording shared by every module (Bangladeshi conventions: en-IN grouping, Tk crore)."""
from __future__ import annotations

from datetime import date

MINUS = "−"


def _group(n: int) -> str:
    """1862400 -> '18,62,400' (Indian grouping)."""
    s = str(abs(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def num(v: float | None, d: int = 1) -> str:
    if v is None:
        return "–"
    r = round(abs(v), d)
    whole = int(r)
    frac = f"{r - whole:.{d}f}"[1:] if d > 0 else ""
    return (MINUS if v < 0 and r != 0 else "") + _group(whole) + frac


def signed(v: float | None, d: int = 1) -> str:
    if v is None:
        return "–"
    if round(v, d) == 0:
        return num(0, d)
    return ("+" if v > 0 else "") + num(v, d)


def pct(v: float | None, d: int = 1) -> str:
    return signed(v, d) + "%" if v is not None else "–"


def tone(v: float | None) -> str:
    """'up', 'down' or 'flat' for colouring (always shown with a sign or arrow as well)."""
    if v is None or v == 0:
        return "flat"
    return "up" if v > 0 else "down"


def day(iso: str) -> str:
    """'2026-11-17' -> 'Tue 17 Nov'."""
    d = date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b}"
