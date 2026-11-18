# Why? write-up contract (format "B + A's thesis", chosen 2026-11-18)

Mockup: `docs/why-formats-mockup.html` (option B, plus option A's Thesis and "What would change our view").
Every word is built by fixed rules from the report's own numbers (no free text, no adjectives the numbers do
not support). Numbers in strings use `dsereport.fmt` (`num`, `pct`, U+2212 minus). Never "None"/"nan" in text.

## Shared shape: a "view"

```json
{
  "badge": "A",                       // setups: grade letter A-D; market cards: "▲" / "▼" / "◆" (up / down / mixed)
  "tone": "up",                       // "up" | "down" | "flat"  (colours the badge)
  "verdict": "Buy on a close at 76.0", // <= 48 chars, imperative for setups, a state for market cards
  "sub": "Medium confidence · 7 evidence points",   // setups; market: "4 of 5 pillars up"
  "thesis": "Two sentences ...",      // A's thesis: what it is, then what we would do or watch
  "pillars": [                        // B's scorecard rows, 4-7 rows
    {"name": "Pattern", "mark": "up", "reading": "Triple Top, one box (+1.1%) from the buy"}
  ],                                  // mark: "up" (✓ for), "down" (✗ against), "flat" (– neutral / not met)
  "plan": [                           // tiles; setups: Entry, Target 1, Target 2, Stop; market: key levels
    {"label": "Entry", "value": 76.0, "pct": 1.1, "tone": "acc"}  // tone: "acc" | "up" | "down" | "flat"; pct may be null
  ],
  "plan_note": "Reward/risk 1.8 : 1. Main risk: a failed breakout that retests 75.0.",  // may be null
  "change_view": "A close below 72.1 (EMA50) before the trigger, or 64.0 (P&F sell) after it.",
  "method": "Rules-based rating from the chart's numbers. Not investment advice."
}
```

## Setups (`report.setups[i].view`) — owner: `dsereport/view.py`

Keep the grading rules already in `view.py` (grade points, confidence, targets). Keep extra keys `grade`,
`confidence`, `points`, `targets` alongside the shape above (the app may use them); drop `why`, `risks`,
`note` (replaced). `badge` = grade; `tone`: A/B "up", C "flat", D "down".
- verdict: "Buy on a close at {entry}"; append ", half size" when there is a caution; for C/D "Watch for a close at {entry}".
- sub: "{confidence} confidence · {points} evidence points".
- thesis (2 sentences): (1) "A close at {entry} completes a {pattern} with {list of met pillars as words} behind it." /
  with a caution: "... ; {caution clause} is against it." (2) "We would buy the print, not the anticipation, and aim
  first at {t1} where the last rally stalled." (no t1: "and aim at {t2}"), C/D: "We would wait for the print and
  more support before acting."
- pillars, in this order, each present: Pattern (always up: "{pattern}, one box ({entry_pct}) from the buy"),
  Trend (up if above EMA50 and EMA200; flat if only one; down if neither; reading with values),
  Momentum (MACD above/below signal), Money flow (MFI now vs five sessions ago), Volume (up if RVOL >= 1.5,
  flat 1.0-1.5, down < 1.0; "{rvol}× average"), Sector (up X column / down O column / flat unknown, with the display
  sector name), Volatility (up squeeze / flat "No squeeze: range is not unusually tight").
- plan: Entry (acc), Target 1 (up, only if t1), Target 2 (up; label "Target" if no t1), Stop (down).
- plan_note: "Reward/risk {rr} : 1. Main risk: {first substantive risk}." (risk rules already in view.py).
- change_view: "A close below {ema50} (EMA50) before the trigger, or {stop} (P&F sell) after it." (no ema50: drop
  the first clause).

## Market cards (`report.periods[p].views`) — owner: new `dsereport/market_view.py`, wired in `build.py` + `schema.py`

`periods[p].views = {"summary": view, "trend": view, "flow": view, "sectors": view, "signals": view}`, built from
the period's own blocks (market, trend, flow, sectors, signals, summary). No grade: badge "▲" (tone up) when more
pillars are up than down, "▼" (down) when more down, "◆" (flat) otherwise. sub: "{n_up} of {n} pillars up".
`plan` = key levels (label/value/pct/tone, pct may be null), plan_note may be null.
- summary: pillars Breadth (adv vs dec), Bullish % (zone + column), Money flow (net Tk cr), Turnover (vs 20-session
  average), Signals (buys vs sells). verdict e.g. "Broad advance, money flowing in". plan: DSEX close, change.
- trend: pillars P&F (status + column), Averages (above how many of EMA20/50/200), Momentum (MACD vs signal, vs zero),
  Breadth (BP column), Trend line (above bullish support = up, below bearish resistance = down).
  verdict e.g. "Recovering, under resistance". plan: P&F reversal level (down), next box (up), trend line (flat).
  change_view from the reversal level and the trend line.
- flow: pillars Net flow, Inflow sessions (of 14), Turnover vs average, Breadth. plan: in / out / net Tk cr (pct null).
- sectors: pillars Leader, Laggard, Sectors in X columns (count of n), Money into the top-flow sector. plan: top 2
  sectors' change (pct).
- signals: pillars Buys vs sells, Beating DSEX (count), Volume surge (count). plan: buys, sells (value = count, pct null).
Week/month periods use the same rules on their own blocks.

## App (`android/app/src/main/assets/ui/app.js`) — owner: UI agent

Sheet layout for any card with a view: verdict box (badge big + verdict + sub) → "Thesis" → "Why?" pillar table
(✓ up / ✗ down / – flat, Pillar, Reading) → "Plan" tiles (setups) or "Levels" tiles (market) → plan_note →
"What would change our view" (left accent bar) → method (small, muted). Then the card's existing detail
(ladder, P&F sketch, tables) below a divider. No "Terms" anywhere. Setup card front keeps the grade chip.
Records and Headlines keep their current sheets (no view). Missing view or fields → skip that block silently.
