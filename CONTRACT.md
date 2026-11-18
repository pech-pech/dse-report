# dsereport build contract (phase 1)

Goal: a Python package that turns the engine's data into the daily report JSON for the DSE Report Android app.
Design it serves: claude.ai/artifact/7cbkEef8zPQaFJuMfYAQNd (cards: summary, participation, trend, money flow,
sectors, signals, one card per breakout setup, record dates, headlines). Plan:
/Users/mmr/pnf-desktop/.claude/worktrees/plugin-check-pgs-hook-52b73d/docs/plans/2026-11-18-dse-report-app.md

## Ground rules (everyone)
- Repo: /Users/mmr/dse-report. Python 3.9 (`from __future__ import annotations`), venv `.venv/bin/python`.
- **Test first.** Write `tests/test_<module>.py` before the module; run `.venv/bin/python -m pytest tests/test_<module>.py -q`
  and `--cov=dsereport.<module>`; target ≥ 80% line coverage for your module. Small hand-made inputs for exact
  numbers; plus one test that runs your function on the real fixture and checks shape and sanity.
- **Pure functions** over the inputs dict `I` (see below). No engine imports except `from screeners import indicators
  as ind` (`ind.ema(values, n)`, `ind.sma`, `ind.macd(closes, slow=26, fast=12, signal=9) -> (line, signal, hist)`,
  `ind.mfi(highs, lows, closes, volumes, n=14)`, `ind.rsi`, `ind.bandwidth`, `ind.rvol`; lists may start with None).
  No network except in `papers.py`. No printing. No mutation of `I` (build new dicts/lists).
- Use `dsereport.periods` (`window(sessions, p)`, `base_session(sessions, p)`, `label`, `future_sessions`) and
  `dsereport.fmt` (`num`, `signed`, `pct`, `tone`, `day`). Do not edit them; ask in your final message if you need more.
- Output must be JSON-serialisable (dicts, lists, str, float rounded to sensible digits, int, bool, None). No NaN.
- Only touch your own files: `dsereport/<module>.py` and `tests/test_<module>.py`. Do not edit others.
- Plain English in every string the reader sees; Bangladeshi units: "Tk 812 crore", "Tk crore" in labels.
- Functions < 50 lines, files < 400 lines, early returns, named constants for thresholds.
- Final message (< 150 words): files written, public functions with signatures, test count and coverage, assumptions.

## The inputs `I` (from `dsereport.source.collect`, saved at tests/fixtures/inputs_2026-11-17.json, 6 MB; load it with
json in tests; do NOT print it whole)
- `asof` "2026-11-17"; `sessions` list[str] last 300 DSE sessions (ascending).
- `dsex`: `dates`, `close` (300); `pf` {`cols`: [[dir "X"/"O", lo_price, hi_price, boxes]] last 7, `reversal` 3};
  `last_signal` {kind BUY/SELL, pattern, date}; `status` "BUY"/"SELL"; `objective` {target, bullish, final, stale};
  `action_points` {column, next (next box price), reverse (3-box reversal price), trigger [kind, price]};
  `stops` {stop, risk_pct}; `trend` "bull"/"bear"; `trend_level`; `chg1w`, `chg1m` (%).
- `market_bp` {signal, since, column, column_since, reading, reverse_at, bp, n, zone}; `bp_series` [[date, bp%]] (300).
- `sector_bp` {sector: same shape as market_bp}; `sector_rows` [{sector, stocks, score, signal, column, trend,
  rs_signal, rs_column, bp, bp_column, bp_signal, bp_zone, buy_pct, mom1, mom3, x_pct}];
  `home_sectors` [{sector, bp, bp_column, chg1d, chg1w, chg1m, score, delta20, ...}];
  `sector_series` {sector: {dates, close (equal-weighted index, 300), members [codes]}}.
- `breadth_today` {stocks, advancers, decliners, new_buys, new_sells, buy_pct, x_pct}; `regime` {key, name, note}.
- `stocks` {code: {code, sector, category, dates, close, high, low, volume (last 60 bars), ema200 (float),
  ema20, ema50, macd, macd_signal, macd_hist, rsi, adx, rvol, bandwidth (last 60, may contain None),
  signal BUY/SELL, pattern, signal_date, column X/O, boxes, target, stop, buy_at (price of the next buy signal),
  sell_at, to_buy (boxes to a buy signal; 0 = on one), to_sell, rs_signal, rs_column, vol_ratio (RVOL today),
  changed [str], chg (today %), turnover (today, Tk mn), trend, stale, pf {cols, reversal}}}.
- `daily` [[code, date, close, prev_close, volume]] for the last 30 sessions (equities). Turnover is NOT stored:
  use volume × close in Tk; crore = Tk / 1e7.
- `events` [{code, kind (cash_dividend|stock_dividend|record_date|earnings|agm|category), date, announced,
  value (dividend % of Tk 10 face, EPS Tk, or None), detail, title}] announced or dated within 45 days of asof, and
  all future dates. A record date's dividend = the cash/stock dividend rows of the same code with the same `announced`.

## Modules and their outputs (period p ∈ "day" | "week" | "month")

1. **flows.py**: `session_rows(I) -> list[dict]` one per session (last 30): {date, adv, dec, unch, turnover_cr,
   in_cr, out_cr, flat_cr, net_cr} (in = turnover of stocks with close > prev_close, out = close < prev_close).
   `period_flow(I, p) -> dict` {sessions, adv, dec, unch, turnover_cr, turnover_avg_cr, vs_avg20 (period's average a
   session ÷ the 20 sessions before the period), in_cr, out_cr, flat_cr, net_cr, last14 [net_cr of the last 14
   sessions, oldest first], inflow_sessions_14 (count > 0), by_sector {sector: net_cr for the period}}.
2. **market.py**: `market_block(I, p) -> dict` {asof, label, dsex {close, chg_pts, chg_pct (vs base_session close)},
   pf {status, column, pattern, signal_date, target, next_box, reverse_at, stop}, bp {value, column, zone, signal,
   column_since, reverse_at, start_value (bp at base_session), path [last 30 bp values]}, regime {name, note},
   levels [{label, text}] (3–4 plain sentences: DSEX next box / reversal, BP vs 50 midline and its reverse_at, and
   where the P&F stop is)}.
3. **trend.py**: `trend_block(I, p) -> dict` {dates, close, ema20, ema50, ema200 (last 60, computed from the 300 DSEX
   closes with ind.ema), macd {line, signal, hist} (last 60), last {close, ema20, ema50, ema200, dist_pct {ema20,
   ema50, ema200}, slope {ema20, ema50, ema200: "rising"/"falling" vs 5 sessions ago}}, cross {kind
   "EMA20 above EMA50"/"EMA20 below EMA50", date} or None (latest within the 60), macd_state {above_signal, above_zero,
   hist_run (int: +N rising N sessions, −N falling), last_signal_cross {kind "above"/"below", date} or None},
   period_sessions (1/len(week)/len(month)), headline (e.g. "Above two of three averages; EMA200 overhead"),
   sentence (one plain sentence naming the averages and MACD state, numbers from the data)}.
4. **sectors.py**: `sector_table(I, p, flow_by_sector) -> list[dict]` rows {sector, chg_pct (period change of the
   sector index from sector_series vs base_session), bp, bp_column, bp_zone, bp_signal, rs_signal, rs_column, net_cr
   (from flow_by_sector, 0 if missing), above_ema50_pct (members whose last close > their ema50[-1]), macd_state
   ("above signal"/"below signal", from ind.macd on the sector index), stocks, score} sorted by chg_pct desc.
   `highlights(rows) -> list[dict]` 3 items {sector, chg_pct, tone, reasons [3–4 short sentences with numbers]}:
   the strongest (BP turn / RS buy / largest inflow), the second, and the weakest (oversold zone or biggest outflow).
5. **signals.py**: `signal_lists(I, p) -> dict` {buys, sells, beating, volume, counts {buys, sells, beating, volume}}.
   buys/sells: stocks whose current signal BUY/SELL has signal_date inside window(p). beating: rs_column "X" and the
   largest period gain over DSEX's. volume: vol_ratio ≥ 2 (today) or the period's average rvol ≥ 2. Each list sorted by
   vol_ratio desc, max 5 items; counts are the full counts. Item: {code, sector, close, chg_pct (period), pattern,
   signal_date, target, stop, rvol, mfi (ind.mfi 14, last), chips [{text, tone}] (MACD "MACD ↑ signal"/"MACD ↓ signal",
   MA "Above EMA50 & EMA200"/"Below EMA50"/…, "MFI 64" (tone warn if ≥80 or ≤20), "Squeeze" warn when bandwidth[-1] ≤
   1.1 × min of the last 60), pf_cols}.
6. **setups.py**: `find_setups(I, k=4) -> list[dict]` candidates: to_buy == 1 (one box from a P&F buy), not stale,
   enough bars; score 7 conditions {one_box, squeeze, macd_above_signal, above_ema50, above_ema200, mfi_rising (mfi[-1] >
   mfi[-6]), sector_bp_rising (sector_bp column X)} → item {code, sector, close, trigger (buy_at), target, cancel
   (sell_at), trigger_pct, target_pct, cancel_pct (vs close), conditions [{key, label, met, help}], score, caution
   (str or None: sector BP in O, or below EMA200), reasoning (2–4 plain sentences built only from the numbers: what the
   P&F shows, momentum/money flow, the caution), pf_cols, rvol}. Rank by score desc, then rvol desc; return top k.
   Labels: "One box from a P&F buy", "Bollinger squeeze", "MACD above signal", "Above EMA50", "Above EMA200",
   "MFI rising", "Sector bullish % rising". `target` is the engine's upside objective only (above the trigger). When it
   is missing, `objective_if` is the vertical count the buy would give if the current X column reaches the trigger
   (from inputs `pending`, engine formula low + R × column size) and `resistance` the first column top above the
   trigger; both with `_pct` vs close and both None when not above the trigger.
7. **events.py**: `record_dates(I, limit=10) -> list[dict]` future record dates (date > asof) ascending: {code,
   record_date, label (fmt.day), sessions_away (via sessions + future_sessions), last_buy (2 sessions before),
   last_buy_label, dividends [{kind "cash"/"stock", pct, tk_per_share (cash: pct/100 × 10)}], dividend_text ("105%
   cash" / "10% stock" / "25% cash + 5% stock" / "No dividend"), declared_on, close, cash_yield_pct, since_declared_pct
   (close vs close on declared_on from stocks dates/close, None if unknown), category}.
   `company_news(I, p, limit=12) -> list[dict]` events announced inside window(p): {date, code, kind label
   ("Results", "Dividend", "Record date", "AGM", "Category"), text (short plain sentence from detail/value, e.g. "Annual
   EPS Tk −0.33 (year to 30 Jun 2026)", "No dividend for the year to 30 Jun 2026", "Moves from Z to A category"),
   move_pct (that code's close vs prev_close on that date from `daily`, None if missing)}; newest first; one item per
   code+announced (merge its rows into one sentence where natural).
8. **papers.py**: `FEEDS` list of (source, section, url): The Daily Star (business/economy/stock, business,
   business/organisation-news rss.xml), TBS (economy/stocks, economy/corporates, economy rss.xml), Prothom Alo English
   (en.prothomalo.com/feed/). `parse_rss(data: bytes, source, section) -> list[dict]` {source, section, title, link,
   published (ISO date or None)} using xml.etree (defusedxml not available: forbid DTDs/entities by rejecting bytes
   containing "<!DOCTYPE" or "<!ENTITY"). `tag(title, codes, sectors) -> list[str]` (codes as whole words,
   case-insensitive; sector names). `fetch(getter=None, timeout=15) -> dict` {fetched_at, items, failed [section
   names]}; `getter(url) -> bytes` injectable (default urllib with a plain User-Agent "dse-report/0.1"); never
   raises for one bad feed; de-duplicate by link; newest first; headline + link only (no descriptions/article text).
   `select(papers, start, end, codes, sectors, limit=12) -> list[dict]` items published within [start, end] with tags.
   Tests use fixture RSS bytes written in the test file (our own sample text), never the network.
9. **brief.py**: `summarize(p, market, trend, flow, sectors, sigs, setups, records) -> dict` using the outputs above:
   {verdict (≤ 6 words, e.g. "Up, with money flowing in" / "Down on thin turnover"), lede (3 sentences: DSEX move and
   turnover vs average, money flow and breadth, leaders/laggards and signal counts), glance [[label, value, change]]
   (DSEX, Up / down, Net money flow Tk cr, Turnover Tk cr, Bullish %), answers 8 [{q, state, tone ("up"/"down"/"flat"),
   detail, card}] for: "Is DSEX in an uptrend?" (pf status + column, card 2), "Are most stocks rising?" (card 1), "Is
   it oversold?" (BP zone, card 1), "Where is money going?" (top sector by net_cr, card 3), "Is momentum building?"
   (MACD state, card 2), "Which sector leads?" (card 4), "What signalled?" (counts, card 5), "What may break out?"
   (len(setups), card 6), notification {title "DSEX +0.61% · 23 buys · 6 sells", lines [5 short lines]}}.
   Every claim must come from the inputs; no adjectives the numbers don't support.

Integrator (not yours): `schema.py`, `build.py`, `cli.py`, card numbering, the final JSON.
