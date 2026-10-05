# MEMORY.md — session handoff

Read this first in a new session; update it before ending one. Static project docs live in
`CLAUDE.md` / `README.md`; this file holds only current state and open work.

Last updated: 2026-10-05

## Where things stand

V1.x implemented and tested. Last commit: `b746c4a` (items 1-3, pushed to origin/main; the branch is `main`, there is no `master`).

## Environment facts (verified 2026-10-05)

- `~/jetson_mount` is mounted and writable (rsync -a prints harmless chgrp errors). The lake is on the Jetson at
  `/storage/stock_market` (495 symbols under `fundamentals/`); `ssh 10.0.0.20` works without a
  password. Don't run recursive `grep` over `/storage` (hangs > 2 min).
- Jetson-side fetcher: `/home/oleg/projects/stock_market/analytics/fundamentals.py` (logs in
  `/storage/stock_market/logs/_fetch.log*`). It collects only 10 concepts. Not modified.
- Open WebUI is already running as a container on the Jetson (`open-webui`), so roadmap item 7 is
  about wiring it to metrics/scores, not installing it.
- The mounted lake is slow; a full factors->backtest rerun takes ~15 min.
- Dry runs: set `STOCK_MARKET_DIR` and `ADVISOR_DATA_DIR` to scratch dirs. Python stdout is
  block-buffered under `nohup`, so a log can look empty while a step runs (use `python -u`).
- `collector.sec_facts` over all 495 symbols takes ~20 min (SEC JSON is large).

## Roadmap

1. [x] TTM + FCF factors. New: `collector/sec_facts.py` (SEC companyfacts -> `advisor/facts_extra/`),
       `derive_quarters()` in `collector/financials.py` (Q2-Q4 from cumulative facts),
       `ttm_sums()` + gross/operating/FCF margin + FCF yield in `quant/factors.py`, wired into scoring
       and `publish/build.py` labels. Checked on AAPL/MSFT/NVDA/JPM (banks have no gross profit: NaN).
2. [x] Transaction costs: `--cost-bps` (default 10) in `quant/backtest.py`.
3. [x] Sector-ETF benchmark (`*_sector_matched` column), needs SPDR ETF prices + universe sectors.
4. [ ] Survivorship bias: needs a point-in-time index-membership source (not chosen).
5. [~] ML score: rank IC now 0.040 with long history; still survivorship-flattered.
6. [ ] `ai/rag.py`: needs filing/transcript text in the lake first.
7. [ ] Open WebUI layer over metrics/scores (container already on the Jetson).
8. [x] Longer history: prices now `--period max` in the lake.

## Last real run (2026-10-05, written to the lake's `advisor/`)

sec_facts, max-history prices (back to ~2009), universe, financials, factors, scoring, model, backtest
for all 495 symbols. ML rank IC 0.040 (positive 59% of months; was 0.005 on 5y of prices). Top-30
backtest 2009-10 to 2026-09, 10 bps costs: `total` CAGR 19.1% / Sharpe 1.33, `ml_score` 35.7% / 1.34,
SPY 14.5% / 1.03. Sector-matched benchmarks: total 13.2%, ml_score 15.3%. Survivorship bias inflates
all of these, so treat the ML CAGR as not credible until item 4 is done.

## Next action

Item 4 (point-in-time universe) is the main thing keeping the backtest from being trustworthy; it
needs a membership source. Then 7 (Open WebUI). 8 is done as a manual run; `scheduler/jobs.py` still
fetches only 1mo of prices and does not run `sec_facts` (add it as a step, e.g. weekly).

## Log

- 2026-10-05: created this file; items 1-3 committed; real run over the lake done (item 8 data, item 5 re-measured).
