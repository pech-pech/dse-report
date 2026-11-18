# DSE Report: report builder

Builds the daily technical report JSON for the DSE Report Android app from the dse-pnf engine (pinned `engine-v1.1`: engine-v1 with DSE at www.dse.com.bd).
Phase 1 of `docs/plans/2026-11-18-dse-report-app.md` (in pnf-desktop). Module contract: `CONTRACT.md`.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/dsereport build --db ~/.dse_pnf/prices.sqlite3 --out out     # reads a copy of the store; ~40 s
.venv/bin/dsereport build --inputs tests/fixtures/inputs_2026-11-17.json --out out --no-papers
.venv/bin/python -m pytest -q --cov=dsereport                            # 207 tests
```

Output: `out/v1/latest.json`, `out/v1/<date>.json`, `out/v1/index.json` (last 60), the files GitHub Pages will serve.
The report is validated (`dsereport/schema.py`) before anything is written.

| Module | Builds |
|---|---|
| `source.py` | the only engine reader: plain inputs from the snapshot, SQL and corporate events |
| `periods.py`, `fmt.py`, `display.py` | day/week/month windows, number wording, sector display names |
| `flows.py` | breadth, turnover (volume × close) and money flow per session and period |
| `market.py`, `trend.py` | DSEX P&F block, bullish percent, levels; EMA20/50/200 and MACD |
| `sectors.py`, `signals.py`, `setups.py` | sector table and highlights; new signals and chips; breakout watch |
| `events.py`, `papers.py` | record dates with declared dividends, company news; newspaper headlines (RSS, https only) |
| `brief.py`, `build.py`, `cli.py` | summary, answers and notification; the report; the command line |

The app must treat headlines and links as untrusted: render text with `textContent`, open only `https` links in the
browser, never in the app's WebView.

## Daily cloud build (`.github/workflows/daily.yml`)

Sun–Thu at 16:50 Dhaka (retry 18:30): restore the price store from the Actions cache (first run: seed from
pnf-desktop's `data` release snapshot), `dsereport refresh` (the engine's own refresh job: prices, sectors, company
news), then `dsereport build --out site --if-newer` and push `v1/` to `gh-pages`. A holiday publishes nothing.
Run it by hand from the Actions tab; `dry_run` keeps the site as a run artifact instead of publishing.

Needs the secret `ENGINE_TOKEN`: a fine-grained token, read-only (Contents: read), for `pech-pech/cl` and
`pech-pech/pnf-desktop`. Report URL: `https://pech-pech.github.io/dse-report/v1/latest.json`.
