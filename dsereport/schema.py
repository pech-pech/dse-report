"""Checks the report JSON before it is published. The app relies on these keys; a failing report is not published."""
from __future__ import annotations

import math
from typing import Any

SCHEMA_VERSION = 1
PERIOD_KEYS = ("label", "sessions", "summary", "market", "trend", "flow", "sectors", "signals", "news", "papers")
SUMMARY_KEYS = ("verdict", "lede", "glance", "answers", "notification")
ANSWERS = 8
MAX_LIST = 5


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


def _check_period(p: str, d: dict, errors: list[str]) -> None:
    path = f"periods.{p}"
    if not _need(d, PERIOD_KEYS, path, errors):
        return
    if _need(d["summary"], SUMMARY_KEYS, f"{path}.summary", errors):
        if len(d["summary"]["answers"]) != ANSWERS:
            errors.append(f"{path}.summary.answers: expected {ANSWERS}")
        if not d["summary"]["lede"].strip():
            errors.append(f"{path}.summary.lede: empty")
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
