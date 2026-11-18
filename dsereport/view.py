"""The analyst view on a breakout setup: grade, confidence, price targets, why, risks, and a short note.

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
FAR_TRIGGER_PCT = 3.0        # a trigger further than this from the close costs a grade point
GRADE_POINTS = ((7, "A"), (5, "B"), (3, "C"))
HIGH_RR = 2.0                # reward/risk needed for High confidence


def _cap(text: str) -> str:
    """First letter up, the rest as written (keeps 'Triple Top', '(O)')."""
    return text[:1].upper() + text[1:]


def _away(pct) -> str:
    return f"{fmt.num(abs(pct), 1)}%" if pct is not None else "an unknown distance"


def _met(item: dict) -> dict:
    return {c["key"]: c["met"] for c in item.get("conditions") or []}


def _rr(entry, target, stop):
    if entry is None or target is None or stop is None or not entry > stop or not target > entry:
        return None
    return round((target - entry) / (entry - stop), 1)


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


def _why(s: dict, item: dict, met: dict, mfi_now, mfi_then) -> list[str]:
    d, close = 1, item.get("close")
    out = [f"{_cap(item.get('pattern') or 'P&F buy')} one box away: a rise to {fmt.num(item['trigger'], d)} "
           f"({fmt.pct(item.get('trigger_pct'))}) completes it."]
    if met.get("above_ema50") and met.get("above_ema200"):
        out.append(f"Trend: above EMA50 ({fmt.num((s.get('ema50') or [None])[-1], d)}) and EMA200 "
                   f"({fmt.num(s.get('ema200'), d)}), so the breakout would run with the longer trend.")
    elif met.get("above_ema50"):
        out.append(f"Trend: above EMA50 ({fmt.num((s.get('ema50') or [None])[-1], d)}), the medium-term line.")
    if met.get("macd_above_signal"):
        out.append("Momentum: MACD is above its signal line.")
    if met.get("mfi_rising") and mfi_now is not None and mfi_then is not None:
        out.append(f"Money flow: MFI {fmt.num(mfi_now, 0)}, up from {fmt.num(mfi_then, 0)} five sessions ago.")
    if (item.get("rvol") or 0) >= VOLUME_CONFIRMS:
        out.append(f"Volume: {fmt.num(item['rvol'], 1)} times its average today, buyers are showing up.")
    if met.get("squeeze"):
        out.append("Range: Bollinger bands near their tightest in 60 sessions; a break tends to travel.")
    if met.get("sector_bp_rising"):
        out.append(f"Sector: {item.get('sector') or 'its sector'} bullish percent is in a rising column.")
    return out


def _risks(item: dict, met: dict, t: dict) -> list[str]:
    d, out = 1, []
    if item.get("caution"):
        out.append(_cap(item["caution"].removeprefix("Caution: ").rstrip(".")) + ".")
    if not met.get("macd_above_signal"):
        out.append("Momentum has not turned: MACD is below its signal line.")
    if not met.get("mfi_rising"):
        out.append("Money flow is not rising (MFI lower than five sessions ago).")
    if (item.get("rvol") or 0) < 1.0:
        out.append("Volume is below average; a breakout on thin volume often fails.")
    if not out:     # nothing against it in the evidence: the risk is the breakout failing
        out.append("A failed breakout: if the trigger prints and the price slips back, P&F buys often retest "
                   "the old top first.")
    if t["stop"] is not None:
        out.append(f"A fall to {fmt.num(t['stop'], d)} ({fmt.pct(t['stop_pct'])}) gives a P&F sell signal; "
                   f"that is the exit.")
    if t["t2_basis"] == "P&F count if triggered":
        out.append("The objective is a P&F count that applies only once the buy signal prints.")
    return out


def _note(s: dict, item: dict, g: str, conf: str, t: dict, why: list[str], risks: list[str]) -> str:
    d = 1
    parts = [f"We rate {item['code']} {g} with {conf.lower()} confidence."]
    parts.append(f"The chart is one box from {('a ' + item['pattern']) if item.get('pattern') else 'a buy signal'} "
                 f"at {fmt.num(t['entry'], d)}, {_away(t['entry_pct'])} above the close of "
                 f"{fmt.num(item.get('close'), d)}; we would act only on that print, not before it.")
    if t["t1"] is not None and t["t2"] is not None:
        parts.append(f"First target {fmt.num(t['t1'], d)} ({fmt.pct(t['t1_pct'])}), where the last rally stalled; "
                     f"second target {fmt.num(t['t2'], d)} ({fmt.pct(t['t2_pct'])}) from the "
                     f"{t['t2_basis']}.")
    elif t["t2"] is not None:
        parts.append(f"Target {fmt.num(t['t2'], d)} ({fmt.pct(t['t2_pct'])}) from the {t['t2_basis']}.")
    if t["stop"] is not None:
        rr = f", for a reward/risk of {fmt.num(t['rr'], 1)} to 1" if t["rr"] is not None else ""
        parts.append(f"Stop at {fmt.num(t['stop'], d)} ({fmt.pct(t['stop_pct'])}), the level that turns the chart "
                     f"to a sell{rr}.")
    support = [w.split(":")[0].lower() for w in why[1:] if ":" in w]
    if support:
        parts.append("In its favour: " + ", ".join(support) + ".")
    if risks:
        main = risks[0]
        parts.append("Main risk: " + main[0].lower() + main[1:])
    return " ".join(parts)


def analyst_view(s: dict, item: dict, mfi_now, mfi_then) -> dict:
    met = _met(item)
    t = targets(item)
    g, points = grade(item)
    conf = confidence(g, t["rr"])
    why = _why(s, item, met, mfi_now, mfi_then)
    risks = _risks(item, met, t)
    return {"grade": g, "points": points, "confidence": conf, "targets": t, "why": why, "risks": risks,
            "note": _note(s, item, g, conf, t, why, risks),
            "method": "Grade and confidence rank the evidence by fixed rules; levels come from the P&F chart. "
                      "Not investment advice."}
