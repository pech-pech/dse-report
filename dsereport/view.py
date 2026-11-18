"""The analyst view on a breakout setup, in the shape of docs/WHY-CONTRACT.md ("Setups").

Every word comes from the setup's own numbers, by the rules below, so two identical charts always read the
same. The grade and confidence are a ranking of the evidence, not a forecast.

Grade points: one per condition met (seven), plus one when today's volume confirms (RVOL >= 1.5), minus one
for a caution (sector bullish % falling or price under EMA200), minus one when the trigger is more than 3%
away. A >= 7, B 5-6, C 3-4, D below.
Confidence: High for an A with reward/risk >= 2; Medium for a B, or an A with less reward/risk; Low otherwise.
"""
from __future__ import annotations

from dsereport import fmt

VOLUME_CONFIRMS = 1.5        # RVOL at or above this counts as volume confirmation
VOLUME_AVERAGE = 1.0         # RVOL below this is thin volume
FAR_TRIGGER_PCT = 3.0        # a trigger further than this from the close costs a grade point
GRADE_POINTS = ((7, "A"), (5, "B"), (3, "C"))
HIGH_RR = 2.0                # reward/risk needed for High confidence
GRADE_TONE = {"A": "up", "B": "up", "C": "flat", "D": "down"}
METHOD = "Rules-based rating from the chart's numbers. Not investment advice."
D = 1                        # decimals for prices


def _met(item: dict) -> dict:
    return {c["key"]: c["met"] for c in item.get("conditions") or []}


def _last(values):
    return values[-1] if values else None


def _rr(entry, target, stop):
    if entry is None or target is None or stop is None or not entry > stop or not target > entry:
        return None
    return round((target - entry) / (entry - stop), 1)


def _words(parts: list[str]) -> str:
    """['a'] -> 'a'; ['a', 'b', 'c'] -> 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def targets(item: dict) -> dict:
    entry = item.get("trigger")
    t2 = item.get("target") if item.get("target") is not None else item.get("objective_if")
    t1 = item.get("resistance")
    if t1 is not None and (entry is None or t1 <= entry or (t2 is not None and t1 >= t2)):
        t1 = None
    stop = item.get("cancel")
    close = item.get("close")

    def pct(v):
        return round((v / close - 1) * 100, 1) if v is not None and close else None
    return {"entry": entry, "entry_pct": pct(entry), "t1": t1, "t1_pct": pct(t1), "t2": t2, "t2_pct": pct(t2),
            "t2_basis": "P&F target" if item.get("target") is not None else "P&F count if triggered",
            "stop": stop, "stop_pct": pct(stop), "rr": _rr(entry, t2, stop)}


def grade(item: dict) -> tuple[str, int]:
    points = sum(1 for v in _met(item).values() if v)
    if (item.get("rvol") or 0) >= VOLUME_CONFIRMS:
        points += 1
    if item.get("caution"):
        points -= 1
    if (item.get("trigger_pct") or 0) > FAR_TRIGGER_PCT:
        points -= 1
    return next((g for floor, g in GRADE_POINTS if points >= floor), "D"), points


def confidence(g: str, rr) -> str:
    if g == "A" and rr is not None and rr >= HIGH_RR:
        return "High"
    if g in ("A", "B"):
        return "Medium"
    return "Low"


# ---- the evidence, one fact per pillar ------------------------------------------------------------------

def _sector_col(item: dict, met: dict, sector_col):
    """'X', 'O' or None. Passed in by setups; otherwise read back from the conditions and the caution."""
    if sector_col in ("X", "O"):
        return sector_col
    if met.get("sector_bp_rising"):
        return "X"
    return "O" if "falling (O) column" in (item.get("caution") or "") else None


def _sector_name(item: dict) -> str:
    return item.get("sector") or "Its sector"


def _ema(name: str, value) -> str:
    return f"{name} {fmt.num(value, D)}" if value is not None else name


def _pattern_pillar(item: dict, t: dict) -> dict:
    pattern = item.get("pattern") or "P&F buy signal"
    box = f"one box ({fmt.pct(t['entry_pct'])})" if t["entry_pct"] is not None else "one box"
    if pattern.endswith(" buy"):
        reading = f"{pattern.removesuffix(' buy')}, {box} from the buy"
    else:
        reading = f"{box[:1].upper()}{box[1:]} from a {pattern}"
    return {"name": "Pattern", "mark": "up", "reading": reading}


def _trend_pillar(s: dict, met: dict) -> dict:
    e50, e200 = _ema("EMA50", _last(s.get("ema50"))), _ema("EMA200", s.get("ema200"))
    above50, above200 = bool(met.get("above_ema50")), bool(met.get("above_ema200"))
    if above50 and above200:
        return {"name": "Trend", "mark": "up", "reading": f"Above {e50} and {e200}"}
    if not above50 and not above200:
        return {"name": "Trend", "mark": "down", "reading": f"Below {e50} and {e200}"}
    reading = f"Above {e50}, below {e200}" if above50 else f"Below {e50}, above {e200}"
    return {"name": "Trend", "mark": "flat", "reading": reading}


def _momentum_pillar(met: dict) -> dict:
    if met.get("macd_above_signal"):
        return {"name": "Momentum", "mark": "up", "reading": "MACD above signal"}
    return {"name": "Momentum", "mark": "down", "reading": "MACD below signal"}


def _flow_pillar(met: dict, mfi_now, mfi_then) -> dict:
    if mfi_now is None or mfi_then is None:
        return {"name": "Money flow", "mark": "flat", "reading": "MFI not available"}
    mark = "up" if met.get("mfi_rising") else "down"
    return {"name": "Money flow", "mark": mark,
            "reading": f"MFI {fmt.num(mfi_now, 0)} ({fmt.num(mfi_then, 0)} a week ago)"}


def _volume_pillar(item: dict) -> dict:
    rvol = item.get("rvol")
    if rvol is None:
        return {"name": "Volume", "mark": "flat", "reading": "Volume not available"}
    mark = "up" if rvol >= VOLUME_CONFIRMS else "flat" if rvol >= VOLUME_AVERAGE else "down"
    return {"name": "Volume", "mark": mark, "reading": f"{fmt.num(rvol, 1)}× average"}


def _sector_pillar(item: dict, col) -> dict:
    name = _sector_name(item)
    if col == "X":
        return {"name": "Sector", "mark": "up", "reading": f"{name} BP rising"}
    if col == "O":
        return {"name": "Sector", "mark": "down", "reading": f"{name} BP in a falling column"}
    return {"name": "Sector", "mark": "flat", "reading": f"{name} BP column not known"}


def _volatility_pillar(met: dict) -> dict:
    if met.get("squeeze"):
        return {"name": "Volatility", "mark": "up", "reading": "Squeeze: tightest in 60 sessions"}
    return {"name": "Volatility", "mark": "flat", "reading": "No squeeze: range is not unusually tight"}


def pillars(s: dict, item: dict, met: dict, t: dict, mfi_now, mfi_then, col) -> list[dict]:
    return [_pattern_pillar(item, t), _trend_pillar(s, met), _momentum_pillar(met),
            _flow_pillar(met, mfi_now, mfi_then), _volume_pillar(item), _sector_pillar(item, col),
            _volatility_pillar(met)]


# ---- the words ------------------------------------------------------------------------------------------

PILLAR_WORDS = {"Trend": "trend", "Momentum": "momentum", "Money flow": "money flow", "Volume": "volume",
                "Sector": "the sector", "Volatility": "a tight range"}


def _against(s: dict, item: dict, met: dict, col) -> list[str]:
    """The caution as noun phrases ('the Bank bullish percent falling', 'the price under its EMA200 (61.5)')."""
    if not item.get("caution"):
        return []
    out = []
    if col == "O":
        out.append(f"the {_sector_name(item)} bullish percent falling")
    if s.get("ema200") is not None and not met.get("above_ema200"):
        out.append(f"the price under its EMA200 ({fmt.num(s['ema200'], D)})")
    if not out:     # a caution from elsewhere: quote it
        text = item["caution"].removeprefix("Caution: ").rstrip(".")
        out.append(text[:1].lower() + text[1:])
    return out


def _thesis(s: dict, item: dict, met: dict, g: str, t: dict, rows: list[dict], col) -> str:
    pattern = item.get("pattern") or "P&F buy signal"
    behind = [PILLAR_WORDS[r["name"]] for r in rows if r["mark"] == "up" and r["name"] in PILLAR_WORDS]
    first = f"A close at {fmt.num(t['entry'], D)} completes a {pattern}"
    first += f" with {_words(behind)} behind it" if behind else " with no other pillar behind it"
    against = _against(s, item, met, col)
    if against:
        first += f"; {_words(against)} {'is' if len(against) == 1 else 'are'} against it"
    if g in ("C", "D"):
        second = "We would wait for the print and more support before acting."
    elif t["t1"] is not None:
        second = (f"We would buy the print, not the anticipation, and aim first at {fmt.num(t['t1'], D)} "
                  f"where the last rally stalled.")
    elif t["t2"] is not None:
        second = f"We would buy the print, not the anticipation, and aim at {fmt.num(t['t2'], D)}."
    else:
        second = "We would buy the print, not the anticipation."
    return f"{first}. {second}"


def _verdict(item: dict, g: str, t: dict) -> str:
    entry = fmt.num(t["entry"], D)
    if g in ("C", "D"):
        return f"Watch for a close at {entry}"
    return f"Buy on a close at {entry}" + (", half size" if item.get("caution") else "")


def _sub(conf: str, points: int) -> str:
    return f"{conf} confidence · {points} evidence point{'' if abs(points) == 1 else 's'}"


def _plan(t: dict) -> list[dict]:
    tiles = [("Entry", t["entry"], t["entry_pct"], "acc")]
    if t["t1"] is not None:
        tiles.append(("Target 1", t["t1"], t["t1_pct"], "up"))
    if t["t2"] is not None:
        tiles.append(("Target 2" if t["t1"] is not None else "Target", t["t2"], t["t2_pct"], "up"))
    if t["stop"] is not None:
        tiles.append(("Stop", t["stop"], t["stop_pct"], "down"))
    return [{"label": lab, "value": v, "pct": p, "tone": tone} for lab, v, p, tone in tiles if v is not None]


def _old_top(item: dict):
    cols = item.get("pf_cols") or []
    return cols[-1][2] if cols and cols[-1][0] == "X" else None


def main_risk(s: dict, item: dict, met: dict, col) -> str:
    """The first risk the evidence shows, in this order: the caution, momentum, money flow, volume; with none
    of those, the risk is the breakout failing."""
    against = _against(s, item, met, col)
    if against:
        return _words(against)
    if not met.get("macd_above_signal"):
        return "momentum has not turned, MACD is below its signal line"
    if not met.get("mfi_rising"):
        return "money flow is not rising"
    if (item.get("rvol") or 0) < VOLUME_AVERAGE:
        return "volume is below average, and thin breakouts often fail"
    top = _old_top(item)
    return "a failed breakout that retests " + (fmt.num(top, D) if top is not None else "the old top")


def _plan_note(s: dict, item: dict, met: dict, t: dict, col) -> str:
    risk = f"Main risk: {main_risk(s, item, met, col)}."
    return f"Reward/risk {fmt.num(t['rr'], 1)} : 1. {risk}" if t["rr"] is not None else risk


def _change_view(s: dict, t: dict):
    ema50 = _last(s.get("ema50"))
    if ema50 is not None and t["stop"] is not None:
        return (f"A close below {fmt.num(ema50, D)} (EMA50) before the trigger, or {fmt.num(t['stop'], D)} "
                f"(P&F sell) after it.")
    if t["stop"] is not None:
        return f"A close below {fmt.num(t['stop'], D)} (P&F sell) after the trigger."
    if ema50 is not None:
        return f"A close below {fmt.num(ema50, D)} (EMA50) before the trigger."
    return None


def analyst_view(s: dict, item: dict, mfi_now, mfi_then, sector_col=None) -> dict:
    met = _met(item)
    col = _sector_col(item, met, sector_col)
    t = targets(item)
    g, points = grade(item)
    conf = confidence(g, t["rr"])
    rows = pillars(s, item, met, t, mfi_now, mfi_then, col)
    return {"badge": g, "tone": GRADE_TONE[g], "verdict": _verdict(item, g, t), "sub": _sub(conf, points),
            "thesis": _thesis(s, item, met, g, t, rows, col), "pillars": rows, "plan": _plan(t),
            "plan_note": _plan_note(s, item, met, t, col), "change_view": _change_view(s, t),
            "method": METHOD, "grade": g, "confidence": conf, "points": points, "targets": t}
