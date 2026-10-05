# MEMORY.md — session handoff

Read this first in a new session; update it before ending one. Static project docs live in
`CLAUDE.md` / `README.md`; this file holds only current state and open work.

Last updated: 2026-10-05

## Where things stand

V1.x implemented and tested. Last commit: `64f8237` (branch is `main`, there is no `master`). Item 4 and 7 are in `64f8237`. **Uncommitted** (45 tests pass): item 6 (`collector/filings.py`, `ai/rag.py`, assistant changes, tests, docs).

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
4. [x] Survivorship bias, partly: membership spells (fja05680/sp500) filter model+backtest to index members at each date; 352 ex-members since 2009 are backfilled where SEC/yfinance have data (~30%), so scored share of members averages 77% (95% latest). Failed/acquired losers without data are still missing, so results remain somewhat optimistic. Final lake run: ML rank IC -0.009 (no skill); top-30 `total` 16.7% CAGR / Sharpe 1.19 vs SPY 14.5% / 1.03 and sector-matched 12.9%; `ml_score` 15.3% / 0.78.
5. [ ] ML score has NO skill once membership is point-in-time (rank IC -0.009). Options: drop it from the site, or rework features/labels. `total` is the only score with any backtest edge.
6. [x] RAG: `collector/filings.py` (latest 10-K/10-Q narrative items -> `advisor/filings/`, 486/495 symbols; 9 skipped: no CIK or no text), `ai/rag.py` (TF-IDF per symbol), used by `assistant/`. Assistant redeployed on the Jetson with it and tested on AAPL tariffs. Filings are not refreshed by `scheduler.jobs` yet (add a step if wanted); research notes don't use rag.
7. [x] Open WebUI layer: `assistant/` is an OpenAI-compatible endpoint (rule-based retrieval of scores/factors/research, forwards to llama.cpp). Deployed 2026-10-05 as container `assistant-sher-advisor-1` on the Jetson, host port 8095 (8090 is taken), code in `~/projects/sher_advisor_assistant` there (copied by rsync; redeploy the same way). STILL TO DO by the user: Open WebUI Admin > Settings > Connections > add `http://10.0.0.20:8095/v1`. Qwen2.5-3B answers are shallow; it has no tool calling.
8. [x] Longer history: prices now `--period max` in the lake.

## News (checked 2026-10-05)

`news/` in the lake is thin: 5,235 IB_NEWS headlines, 484 symbols (~11 each), almost all since 2024-08 (dense only from 2025-07), no bodies, a gap 2026-03-06 to 2026-06-22. About 74% are broker actions (upgraded/downgraded/initiated/reiterated with target price). Headlines carry a `{A:..:K:<sentiment>:C:..}` tag; `collector.store.clean_news` strips it and exposes `sentiment` (only ~45% have one). Too short and sparse for a news factor in the 12-month model. Used instead in `assistant/` (recent headlines + 180-day broker action counts) and, now cleaned, in research notes. Other lake folders (processed intraday bars, accumulation, engulfing, ...) are still unused; see the survey in the chat: processed/ has 5s-style bars for 549 symbols since 2025-08, accumulation/ has features/scores/labels (not inspected for point-in-time safety).

## Next action

Decide on item 5 (ML has no skill) and whether to add a filings step to the scheduler. The user adds the Open WebUI
connection by hand (item 7). The scheduler now runs membership, sec_facts and deploy steps; nothing
schedules it (user runs it manually).

## Log

- 2026-10-05: created this file; items 1-3 committed; real run over the lake done (item 8 data, item 5 re-measured).
