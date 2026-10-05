# MEMORY.md — session handoff

Read this first in a new session; update it before ending one. Static project docs live in
`CLAUDE.md` / `README.md`; this file holds only current state and open work.

Last updated: 2026-10-05

## Where things stand

V1.x implemented and tested. Last commit: `005be63`. **Uncommitted work from 2026-10-05** (user has
not asked for a commit): items 1-3 below, 29 tests passing.

## Environment facts (verified 2026-10-05)

- `~/jetson_mount` is NOT mounted (empty dir). The lake is on the Jetson at
  `/storage/stock_market` (495 symbols under `fundamentals/`); `ssh 10.0.0.20` works without a
  password. Don't run recursive `grep` over `/storage` (hangs > 2 min).
- Jetson-side fetcher: `/home/oleg/projects/stock_market/analytics/fundamentals.py` (logs in
  `/storage/stock_market/logs/_fetch.log*`). It collects only 10 concepts. Not modified.
- Open WebUI is already running as a container on the Jetson (`open-webui`), so roadmap item 7 is
  about wiring it to metrics/scores, not installing it.
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
5. [ ] ML score skill (rank IC ~0.005 before). Re-measure after item 8 and the new factors.
6. [ ] `ai/rag.py`: needs filing/transcript text in the lake first.
7. [ ] Open WebUI layer over metrics/scores (container already on the Jetson).
8. [ ] Longer history: run `collector.market --period max`; `scheduler/jobs.py` only fetches 1mo daily.

## In flight / next action

A full dry run (495 symbols) was started in scratchpad: sec_facts -> financials -> market (max) ->
universe -> factors -> scoring -> model -> backtest, log in the scratchpad `dryrun.log`. If it
finished, its output shows the new rank IC and backtest with costs. Nothing was written to the real
lake. To apply for real: mount the lake (or point env vars at it), then run the same commands.

## Log

- 2026-10-05: created this file; added items 1-3; docs (CLAUDE.md, README.md, quant/README.md) updated.
