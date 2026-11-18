"""Card 7: upcoming record dates with the dividend declared, and company news in plain sentences."""
from __future__ import annotations

import re
from datetime import date

from dsereport import fmt, periods

KIND_LABELS = {"cash_dividend": "Dividend", "stock_dividend": "Dividend", "earnings": "Results",
               "record_date": "Record date", "agm": "AGM", "category": "Category"}
OTHER_LABEL = "Notice"
LABELS = ("Dividend", "Results", "Record date", "AGM", "Category", OTHER_LABEL)
KIND_ORDER = ("earnings", "cash_dividend", "stock_dividend", "record_date", "agm", "category")
DIVIDEND_KINDS = {"cash_dividend": "cash", "stock_dividend": "stock"}
FACE_VALUE_TK = 10.0
SETTLEMENT_SESSIONS = 2          # T+2: the last day to buy is two sessions before the record date
PLAIN_RECORD_NOTICE = "Dividend Declaration"

_NUM = r"(\(?[\d.]+\)?)"
_PERIOD_RE = re.compile(r"year/period ended (\d{4}-\d{2}-\d{2})")
_ANNUAL_RE = re.compile(r"^annual results for year/period ended [\d-]+: EPS Tk " + _NUM + "$")
_QUARTER_RE = re.compile(r"^Q(\d) results: EPS Tk " + _NUM + r"(?:; cumulative EPS Tk " + _NUM + ")?$")
_QUARTER_BARE_RE = re.compile(r"^Q(\d) results \(EPS not parsed\)$")
_PCT_DIV_RE = re.compile(r"^([\d.]+)% (final )?(cash|stock)( \(interim\))?( \(excl\. sponsors/directors\))?")
_TK_DIV_RE = re.compile(r"^Tk ([\d.]+) per share/unit cash")
_RECORD_RE = re.compile(r"^record date \((.*)\)$")
_CATEGORY_RE = re.compile(r"^(\w+) -> (\w+)$")


# ---------- sentence parts: (text, period or None, period style "paren" | "for") ----------

def _tk(s: str) -> float:
    """'0.76' -> 0.76, '(0.33)' -> -0.33 (accounts brackets mean a loss)."""
    v = float(s.strip("()"))
    return -v if s.startswith("(") else v


def _period(detail: str) -> str | None:
    m = _PERIOD_RE.search(detail)
    if not m:
        return None
    d = date.fromisoformat(m.group(1))
    return f"year to {d.day} {d:%b} {d.year}"


def _earnings_part(row: dict) -> tuple | None:
    detail = row.get("detail") or ""
    m = _ANNUAL_RE.match(detail)
    if m:
        return f"Annual EPS Tk {fmt.num(_tk(m.group(1)), 2)}", _period(detail), "paren"
    m = _QUARTER_RE.match(detail)
    if m:
        text = f"Q{m.group(1)} EPS Tk {fmt.num(_tk(m.group(2)), 2)}"
        if m.group(3):
            text += f" (cumulative Tk {fmt.num(_tk(m.group(3)), 2)})"
        return text, None, "paren"
    m = _QUARTER_BARE_RE.match(detail)
    return (f"Q{m.group(1)} results published", None, "paren") if m else None


def _dividend_part(row: dict) -> tuple | None:
    detail = row.get("detail") or ""
    period = _period(detail)
    if detail.startswith("no dividend"):
        return "No dividend", period, "for"
    m = _PCT_DIV_RE.match(detail)
    if m:
        pct, final, kind, interim, excl = m.groups()
        text = f"{pct}% {'interim ' if interim else ''}{final or ''}{kind} dividend"
        return text + (", sponsors/directors excluded" if excl else ""), period, "paren"
    m = _TK_DIV_RE.match(detail)
    return (f"Tk {m.group(1)} a share cash dividend", period, "paren") if m else None


def _record_part(row: dict) -> tuple | None:
    m = _RECORD_RE.match(row.get("detail") or "")
    if not m or not row.get("date"):
        return None
    text = f"Record date {fmt.day(row['date'])}"
    return (text if m.group(1) == PLAIN_RECORD_NOTICE else f"{text} ({m.group(1)})"), None, "paren"


def _agm_part(row: dict) -> tuple | None:
    detail = row.get("detail") or ""
    if detail not in ("AGM", "EGM") or not row.get("date"):
        return None
    return f"{detail} {fmt.day(row['date'])}", None, "paren"


def _category_part(row: dict) -> tuple | None:
    m = _CATEGORY_RE.match(row.get("detail") or "")
    return (f"Moves from {m.group(1)} to {m.group(2)} category", None, "paren") if m else None


_PARTS = {"earnings": _earnings_part, "cash_dividend": _dividend_part, "stock_dividend": _dividend_part,
          "record_date": _record_part, "agm": _agm_part, "category": _category_part}


def _part(row: dict) -> tuple:
    """A row's sentence part; unknown wording falls back to the notice title."""
    parser = _PARTS.get(row.get("kind"))
    found = parser(row) if parser else None
    return found or ((row.get("title") or row.get("detail") or "").strip(), None, "paren")


def _render(part: tuple, show_period: bool) -> str:
    text, period, style = part
    if not (show_period and period):
        return text
    return f"{text} for the {period}" if style == "for" else f"{text} ({period})"


def event_text(row: dict) -> str:
    """One event row as a short plain sentence."""
    return _render(_part(row), True)


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def _order_key(row: dict) -> tuple[int, str]:
    """Kind order; within results the annual figure first, then Q1, Q2, Q3."""
    kind = row.get("kind")
    rank = KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)
    detail = row.get("detail") or ""
    return rank, ("" if detail.startswith("annual") else detail) if kind == "earnings" else ""


def merged_text(rows: list[dict]) -> str:
    """Several rows of one announcement as one sentence; each period is named once."""
    ordered = sorted(rows, key=_order_key)
    texts, shown = [], set()
    for row in ordered:
        part = _part(row)
        text = _render(part, part[1] not in shown)
        shown.add(part[1])
        if text and text not in texts:
            texts.append(text if not texts else _lower_first(text))
    return "; ".join(texts)


# ---------- prices ----------

def _series(I: dict, code: str) -> list[tuple[str, float]]:
    """(date, close) ascending: the stock's 60 bars, else its rows in `daily`."""
    st = (I.get("stocks") or {}).get(code)
    if st and st.get("dates") and st.get("close"):
        return [(d, c) for d, c in zip(st["dates"], st["close"]) if c is not None]
    return sorted((r[1], r[2]) for r in I.get("daily") or [] if r[0] == code and r[2] is not None)


def _close_on(series: list[tuple[str, float]], iso: str) -> float | None:
    """The last close on or before ``iso`` (None when the data starts after it)."""
    before = [c for d, c in series if d <= iso]
    return before[-1] if before else None


def _change_pct(now: float | None, then: float | None) -> float | None:
    if not now or not then:
        return None
    return round((now / then - 1) * 100, 2)


# ---------- record dates ----------

def _dividends(rows: list[dict]) -> tuple[list[dict], bool]:
    """Declared dividends from the cash/stock rows, and whether a 'no dividend' row was seen."""
    out, none_declared = [], False
    for row in rows:
        kind = DIVIDEND_KINDS[row["kind"]]
        pct = row.get("value")
        m = _TK_DIV_RE.match(row.get("detail") or "")
        if pct is None and m:
            pct = float(m.group(1)) / FACE_VALUE_TK * 100
        if not pct:
            none_declared = none_declared or (row.get("detail") or "").startswith("no dividend")
            continue
        tk = round(pct / 100 * FACE_VALUE_TK, 2) if kind == "cash" else None
        out.append({"kind": kind, "pct": round(float(pct), 2), "tk_per_share": tk})
    return out, none_declared


def _dividend_text(divs: list[dict], none_declared: bool, title: str) -> str:
    if divs:
        return " + ".join(f"{d['pct']:g}% {d['kind']}" for d in divs)
    if none_declared:
        return "No dividend"
    return f"No dividend found; notice: {title}"


def _session_info(I: dict, record_date: str) -> dict:
    asof = I["asof"]
    days_ahead = (date.fromisoformat(record_date) - date.fromisoformat(asof)).days
    future = [s for s in periods.future_sessions(asof, max(days_ahead, 1)) if s <= record_date]
    known = [s for s in I.get("sessions") or [] if s <= asof] + future
    idx = len(known) - 1 - SETTLEMENT_SESSIONS
    last_buy = known[idx] if idx >= 0 else None
    return {"sessions_away": len(future), "last_buy": last_buy,
            "last_buy_label": fmt.day(last_buy) if last_buy else None,
            "can_still_buy": bool(last_buy and last_buy > asof)}


def _record_item(I: dict, rec: dict) -> dict:
    code, declared = rec["code"], rec.get("announced")
    div_rows = [e for e in I.get("events") or []
                if e.get("code") == code and e.get("announced") == declared and e.get("kind") in DIVIDEND_KINDS]
    divs, none_declared = _dividends(div_rows)
    series = _series(I, code)
    close = series[-1][1] if series else None
    cash_tk = sum(d["tk_per_share"] for d in divs if d["kind"] == "cash")
    stock = (I.get("stocks") or {}).get(code) or {}
    return {"code": code, "record_date": rec["date"], "label": fmt.day(rec["date"]),
            **_session_info(I, rec["date"]),
            "dividends": divs, "dividend_text": _dividend_text(divs, none_declared, rec.get("title") or ""),
            "declared_on": declared, "close": close,
            "cash_yield_pct": round(cash_tk / close * 100, 2) if cash_tk and close else None,
            "since_declared_pct": _change_pct(close, _close_on(series, declared)) if declared else None,
            "category": stock.get("category")}


def record_dates(I: dict, limit: int = 10) -> list[dict]:
    """Future record dates (after asof), soonest first, one per code and date."""
    asof, seen, recs = I["asof"], set(), []
    rows = [e for e in I.get("events") or [] if e.get("kind") == "record_date" and (e.get("date") or "") > asof]
    for rec in sorted(rows, key=lambda e: (e["date"], e["code"])):
        if (rec["code"], rec["date"]) not in seen:
            seen.add((rec["code"], rec["date"]))
            recs.append(rec)
    return [_record_item(I, rec) for rec in recs[:limit]]


# ---------- company news ----------

def _label(rows: list[dict]) -> str:
    kinds = [KIND_LABELS.get(r.get("kind"), OTHER_LABEL) for r in rows]
    return next((lab for lab in LABELS if lab in kinds), OTHER_LABEL)


def _move_pct(I: dict, code: str, iso: str) -> float | None:
    for row in I.get("daily") or []:
        if row[0] == code and row[1] == iso:
            return _change_pct(row[2], row[3])
    return None


def company_news(I: dict, p: str, limit: int = 12) -> list[dict]:
    """Announcements after the period's base session up to asof, newest first, one item per code and day."""
    w = periods.window(I["sessions"], p)
    if not w:
        return []
    base = periods.base_session(I["sessions"], p)
    asof = I["asof"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in I.get("events") or []:
        ann = e.get("announced") or ""
        if (ann > base if base else ann >= w[0]) and ann <= asof:
            groups.setdefault((ann, e["code"]), []).append(e)
    keys = sorted(groups, key=lambda k: (-date.fromisoformat(k[0]).toordinal(), k[1]))[:limit]
    return [{"date": ann, "code": code, "kind": _label(groups[(ann, code)]),
             "text": merged_text(groups[(ann, code)]), "move_pct": _move_pct(I, code, ann)}
            for ann, code in keys]
