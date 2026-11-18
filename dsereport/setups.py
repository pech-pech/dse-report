"""Watch out for: stocks one box from a P&F buy, scored on seven plain conditions."""
from __future__ import annotations

from screeners import indicators as ind

from dsereport import fmt, view

MIN_BARS = 20            # MFI(14) needs 14 bars, plus 6 to compare with five sessions ago
MFI_N = 14
MFI_LOOKBACK = 5         # mfi[-1] vs mfi[-6]
SQUEEZE_FACTOR = 1.1     # bandwidth within 10% of its 60-bar low
SQUEEZE_BARS = 60

CONDITIONS = (
    ("one_box", "One box from a P&F buy",
     "The point and figure chart needs a rise of only one more box to give a buy signal."),
    ("squeeze", "Bollinger squeeze",
     "The Bollinger bands are within 10% of their narrowest width of the last 60 sessions, so the price range is tight."),
    ("macd_above_signal", "MACD above signal",
     "The MACD line is above its signal line, which shows short-term momentum is stronger than its recent average."),
    ("above_ema50", "Above EMA50",
     "The last close is above the 50-day exponential moving average, the medium-term trend line."),
    ("above_ema200", "Above EMA200",
     "The last close is above the 200-day exponential moving average, the long-term trend line."),
    ("mfi_rising", "MFI rising",
     "The Money Flow Index, which weighs price moves by volume, is higher than five sessions ago."),
    ("sector_bp_rising", "Sector bullish % rising",
     "The share of stocks in this sector on P&F buy signals is in a rising (X) column."),
)
CONDITION_KEYS = tuple(c[0] for c in CONDITIONS)


def _last(values):
    return values[-1] if values else None


def _gt(a, b) -> bool:
    return a is not None and b is not None and a > b


def _pct(price, close):
    if not price or not close:
        return None
    return round((price / close - 1) * 100, 1)


def _squeeze(bandwidth) -> bool:
    recent = [b for b in (bandwidth or [])[-SQUEEZE_BARS:] if b is not None]
    last = _last(bandwidth or [])
    return last is not None and bool(recent) and last <= SQUEEZE_FACTOR * min(recent)


def _mfi_pair(s):
    """MFI now and MFI_LOOKBACK sessions ago; (None, None) when a bar is missing a value."""
    try:
        m = ind.mfi(s["high"], s["low"], s["close"], s["volume"], MFI_N)
        return m[-1], m[-1 - MFI_LOOKBACK]
    except (KeyError, TypeError, ZeroDivisionError, IndexError):
        return None, None


def _is_candidate(s) -> bool:
    return (s.get("to_buy") == 1 and not s.get("stale") and bool(s.get("buy_at"))
            and len(s.get("close") or []) >= MIN_BARS)


def _met(s, sector_col, mfi_now, mfi_then) -> dict:
    close = s["close"][-1]
    return {
        "one_box": s.get("to_buy") == 1,
        "squeeze": _squeeze(s.get("bandwidth")),
        "macd_above_signal": _gt(_last(s.get("macd")), _last(s.get("macd_signal"))),
        "above_ema50": _gt(close, _last(s.get("ema50"))),
        "above_ema200": _gt(close, s.get("ema200")),
        "mfi_rising": _gt(mfi_now, mfi_then),
        "sector_bp_rising": sector_col == "X",
    }


def _caution(s, sector_col) -> str | None:
    parts = []
    if sector_col == "O":
        parts.append(f"the {s['sector']} bullish percent is in a falling (O) column")
    if s.get("ema200") is not None and not _gt(s["close"][-1], s["ema200"]):
        parts.append(f"the price is below its EMA200 ({fmt.num(s.get('ema200'), 2)})")
    if not parts:
        return None
    return "Caution: " + " and ".join(parts) + "."


def _buy_name(cols) -> str:
    """'Double Top buy' / 'Triple Top buy' when earlier X columns topped at the current X column's high."""
    if not cols or cols[-1][0] != "X":
        return "a P&F buy signal"
    top = cols[-1][2]
    equal = 0
    for col in reversed([c for c in cols[:-1] if c[0] == "X"]):
        if col[2] != top:
            break
        equal += 1
    if equal == 0:
        return "a P&F buy signal"
    return "a Double Top buy" if equal == 1 else "a Triple Top buy"


def _reasoning(s, item, mfi_now, mfi_then) -> list[str]:
    d = 1
    first = (f"{s['code']} is one box from a P&F buy: a rise to {fmt.num(item['trigger'], d)} would give "
             f"{_buy_name(item['pf_cols'])}, {fmt.pct(item['trigger_pct'])} from the last close of "
             f"{fmt.num(item['close'], d)}.")
    old = s.get("target")
    if item["target"] is None and item["objective_if"] is not None:
        second = (f"If {fmt.num(item['trigger'], d)} triggers, the P&F count points to about "
                  f"{fmt.num(item['objective_if'], d)} ({fmt.pct(item['objective_if_pct'])})")
        if item["resistance"] is not None:
            second += f", with resistance first at {fmt.num(item['resistance'], d)}"
    elif item["target"] is None and old:
        second = (f"The P&F objective of {fmt.num(old, d)} comes from the current {s.get('signal', 'sell').lower()} "
                  f"signal and lies below the trigger, so no upside target is shown")
    elif item["target"] is None:
        second = "There is no P&F price objective in the data, so no target is shown"
    else:
        second = f"The P&F count gives a target of {fmt.num(item['target'], d)} ({fmt.pct(item['target_pct'])})"
    if item["cancel"] is not None:
        second += f"; a fall to {fmt.num(item['cancel'], d)} ({fmt.pct(item['cancel_pct'])}) would give a sell signal"
    macd = "above" if item["_macd"] else "below"
    third = (f"MACD is {macd} its signal line, MFI is {fmt.num(mfi_now, 0)} against {fmt.num(mfi_then, 0)} "
             f"five sessions ago, and today's volume is {fmt.num(item['rvol'], 1)} times its average.")
    out = [first, second + ".", third]
    if item["caution"]:
        out.append(item["caution"])
    return out


def _item(s, sector_bp) -> dict:
    sector_col = (sector_bp.get(s.get("sector")) or {}).get("column")
    mfi_now, mfi_then = _mfi_pair(s)
    met = _met(s, sector_col, mfi_now, mfi_then)
    close = s["close"][-1]
    target = s.get("target") if _gt(s.get("target"), s["buy_at"]) else None   # an upside objective only
    cancel = s.get("sell_at") or None
    pending = s.get("pending") or {}
    objective_if = pending.get("objective") if target is None and _gt(pending.get("objective"), s["buy_at"]) else None
    resistance = pending.get("resistance") if _gt(pending.get("resistance"), s["buy_at"]) else None
    item = {
        "code": s["code"], "sector": s.get("sector"), "close": close,
        "trigger": s["buy_at"], "target": target, "cancel": cancel,
        "trigger_pct": _pct(s["buy_at"], close), "target_pct": _pct(target, close),
        "cancel_pct": _pct(cancel, close),
        "objective_if": objective_if, "objective_if_pct": _pct(objective_if, close),
        "resistance": resistance, "resistance_pct": _pct(resistance, close),
        "conditions": [{"key": k, "label": lab, "met": met[k], "help": h} for k, lab, h in CONDITIONS],
        "score": sum(1 for k in CONDITION_KEYS if met[k]),
        "caution": _caution(s, sector_col),
        "pf_cols": [list(c) for c in (s.get("pf") or {}).get("cols", [])],
        "rvol": s.get("vol_ratio"),
        "_macd": met["macd_above_signal"],
    }
    item["pattern"] = _buy_name(item["pf_cols"]).removeprefix("a ")
    item["reasoning"] = _reasoning(s, item, mfi_now, mfi_then)
    del item["_macd"]
    item["view"] = view.analyst_view(s, item, mfi_now, mfi_then)
    return item


def find_setups(I: dict, k: int = 4) -> list[dict]:
    """Stocks one box from a P&F buy, ranked by conditions met, then by today's relative volume."""
    sector_bp = I.get("sector_bp") or {}
    items = [_item(s, sector_bp) for s in I.get("stocks", {}).values() if _is_candidate(s)]
    items.sort(key=lambda i: (i["score"], i["rvol"] or 0), reverse=True)
    return items[:k]
