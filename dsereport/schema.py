"""Checks the report JSON before it is published. The app relies on these keys; a failing report is not published."""
from __future__ import annotations

import math
from typing import Any

SCHEMA_VERSION = 1
PERIOD_KEYS = ("label", "sessions", "summary", "market", "trend", "flow", "sectors", "signals", "news", "papers", "views")
SUMMARY_KEYS = ("verdict", "lede", "glance", "answers", "notification")
ANSWERS = 8
MAX_LIST = 5
MARKET_CARDS = ("summary", "trend", "flow", "sectors", "signals")
VIEW_KEYS = ("badge", "tone", "verdict", "sub", "thesis", "pillars", "plan", "plan_note", "change_view", "method")
MARKET_BADGES = ("▲", "▼", "◆")
TONES = ("up", "down", "flat")
PLAN_TONES = ("acc", "up", "down", "flat")
MAX_VERDICT = 48
MIN_PILLARS = 3
BAD_WORDS = ("None", "nan")


def _walk(v: Any, path: str, errors: list[str]) -> None:
    if isinstance(v, float) and not math.isfinite(v):
        errors.append(f"{path}: not a finite number")
    elif isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                errors.append(f"{path}: non-string key {k!r}")
            _walk(x, f"{path}.{k}", errors)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _walk(x, f"{path}[{i}]", errors)
    elif not (v is None or isinstance(v, (str, int, float, bool))):
        errors.append(f"{path}: unsupported type {type(v).__name__}")


def _need(d: Any, keys, path: str, errors: list[str]) -> bool:
    if not isinstance(d, dict):
        errors.append(f"{path}: expected an object")
        return False
    missing = [k for k in keys if k not in d]
    if missing:
        errors.append(f"{path}: missing {', '.join(missing)}")
    return not missing


def _text(v: Any, path: str, errors: list[str], optional: bool = False) -> None:
    if v is None and optional:
        return
    if not isinstance(v, str) or not v.strip():
        errors.append(f"{path}: expected text")
    elif any(w in v.replace(",", " ").replace(".", " ").split() for w in BAD_WORDS):
        errors.append(f"{path}: contains None or nan")


def _check_pillars(pillars: Any, path: str, errors: list[str]) -> None:
    if not isinstance(pillars, list) or len(pillars) < MIN_PILLARS:
        errors.append(f"{path}: expected at least {MIN_PILLARS} pillars")
        return
    for i, x in enumerate(pillars):
        if _need(x, ("name", "mark", "reading"), f"{path}[{i}]", errors):
            _text(x["name"], f"{path}[{i}].name", errors)
            _text(x["reading"], f"{path}[{i}].reading", errors)
            if x["mark"] not in TONES:
                errors.append(f"{path}[{i}].mark: expected up, down or flat")


def _check_plan(plan: Any, path: str, errors: list[str]) -> None:
    if not isinstance(plan, list):
        errors.append(f"{path}: expected a list")
        return
    for i, x in enumerate(plan):
        if _need(x, ("label", "value", "pct", "tone"), f"{path}[{i}]", errors):
            _text(x["label"], f"{path}[{i}].label", errors)
            if not isinstance(x["value"], (int, float)) or not (x["pct"] is None or isinstance(x["pct"], (int, float))):
                errors.append(f"{path}[{i}]: value must be a number, pct a number or null")
            if x["tone"] not in PLAN_TONES:
                errors.append(f"{path}[{i}].tone: expected acc, up, down or flat")


def check_view(v: Any, path: str, errors: list[str], badges=MARKET_BADGES) -> None:
    """One "Why?" view (docs/WHY-CONTRACT.md); None is allowed (the app then skips the block)."""
    if v is None or not _need(v, VIEW_KEYS, path, errors):
        return
    if v["badge"] not in badges:
        errors.append(f"{path}.badge: unexpected {v['badge']!r}")
    if v["tone"] not in TONES:
        errors.append(f"{path}.tone: expected up, down or flat")
    for k in ("verdict", "sub", "thesis", "change_view", "method"):
        _text(v[k], f"{path}.{k}", errors)
    _text(v["plan_note"], f"{path}.plan_note", errors, optional=True)
    if isinstance(v["verdict"], str) and len(v["verdict"]) > MAX_VERDICT:
        errors.append(f"{path}.verdict: longer than {MAX_VERDICT}")
    _check_pillars(v["pillars"], f"{path}.pillars", errors)
    _check_plan(v["plan"], f"{path}.plan", errors)


def _check_views(views: Any, path: str, errors: list[str]) -> None:
    if not _need(views, MARKET_CARDS, path, errors):
        return
    for card in MARKET_CARDS:
        check_view(views[card], f"{path}.{card}", errors)


def _check_period(p: str, d: dict, errors: list[str]) -> None:
    path = f"periods.{p}"
    if not _need(d, PERIOD_KEYS, path, errors):
        return
    if _need(d["summary"], SUMMARY_KEYS, f"{path}.summary", errors):
        if len(d["summary"]["answers"]) != ANSWERS:
            errors.append(f"{path}.summary.answers: expected {ANSWERS}")
        if not d["summary"]["lede"].strip():
            errors.append(f"{path}.summary.lede: empty")
    _check_views(d["views"], f"{path}.views", errors)
    sig = d["signals"]
    if _need(sig, ("buys", "sells", "beating", "volume", "counts"), f"{path}.signals", errors):
        for k in ("buys", "sells", "beating", "volume"):
            if len(sig[k]) > MAX_LIST:
                errors.append(f"{path}.signals.{k}: more than {MAX_LIST}")


def validate(report: Any) -> list[str]:
    """Every problem found, as plain sentences; an empty list means the report can be published."""
    errors: list[str] = []
    if not _need(report, ("schema", "asOf", "builtAt", "periods", "setups", "records", "notification"), "report", errors):
        return errors
    if report["schema"] != SCHEMA_VERSION:
        errors.append(f"report.schema: expected {SCHEMA_VERSION}")
    for p in ("day", "week", "month"):
        if p not in report["periods"]:
            errors.append(f"periods: missing {p}")
        else:
            _check_period(p, report["periods"][p], errors)
    _walk(report, "report", errors)
    return errors
