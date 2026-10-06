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
7. [x] Open WebUI layer: `assistant/` is an OpenAI-compatible endpoint (rule-based retrieval of scores/factors/research, forwards to llama.cpp). Deployed 2026-10-05 as container `assistant-sher-advisor-1` on the Jetson, host port 8095 (8090 is taken), code in `~/projects/sher_advisor_assistant` there (copied by rsync; redeploy the same way). The user added the connection `http://10.0.0.20:8095/v1` in Open WebUI and confirmed it works (2026-10-05). Qwen2.5-3B answers are shallow; it has no tool calling.
8. [x] Longer history: prices now `--period max` in the lake.

## News (checked 2026-10-05)

`news/` in the lake is thin: 5,235 IB_NEWS headlines, 484 symbols (~11 each), almost all since 2024-08 (dense only from 2025-07), no bodies, a gap 2026-03-06 to 2026-06-22. About 74% are broker actions (upgraded/downgraded/initiated/reiterated with target price). Headlines carry a `{A:..:K:<sentiment>:C:..}` tag; `collector.store.clean_news` strips it and exposes `sentiment` (only ~45% have one). Too short and sparse for a news factor in the 12-month model. Used instead in `assistant/` (recent headlines + 180-day broker action counts) and, now cleaned, in research notes. Other lake folders (processed intraday bars, accumulation, engulfing, ...) are still unused; see the survey in the chat: processed/ has 5s-style bars for 549 symbols since 2025-08, accumulation/ was tested (below).

`accumulation/` (checked 2026-10-05): daily, ~5,200 tickers, features/scores 2023-10-23..2026-10-02, labels (60-bar forward return, `label_30in60`) to 2026-07-09. Features are trailing, labels forward (consistent). Rank IC of every feature and of its rule-based `score` vs 60-bar forward return minus the monthly median, month-ends only (34 months), restricted to our 491 lake symbols: nothing significant (best |t| 1.7; `score` IC -0.017). Across the full small/micro-cap universe there are strong effects (liquidity, low volatility, distance from 60d high; |t| up to 9) but that is a size/liquidity premium and their own model notes say backfilled rows lack delisted losers. Verdict: no use as a factor for the S&P research universe. Its `ml_prob` in historic score files may be in-sample, so it was not tested.

`scorecard/` (checked 2026-10-05): the other system's live paper-trading ledger, 2026-07-27..2026-10-02, 3,053 recommendations (accumulation 980, oem 961, gainers 492, candidates 352, indicator_models 215, levered 42, pairs 11), with TP/SL bracket outcomes at h1/h5/h20. Resolved h20 bracket net return: accumulation -1.0% (hit 31%, its own leaderboard t -3.1), candidates -1.4%, gainers -1.9%, oem -0.5%, indicator_models +3.6% (hit 43%, n=184), levered +1.6% (n=42). So the accumulation module that looked good in backtest (AUC 0.78) loses live, matching our no-factor finding. Our `total` top-30 over the same window (2 month-end cross-sections, 20 sessions): Jul +0.5% vs universe +2.8%, Aug -5.4% vs -4.4%, i.e. behind both times; far too short to conclude anything (the 2009-2026 backtest is the evidence). No comparison of picks is meaningful at this sample size; revisit after ~6+ months of ledger.

## Jetson pipeline container (in progress, 2026-10-05)

`scheduler/Dockerfile` + `scheduler/docker-compose.yml` (mem 2g, lake read-only except `advisor/`, entrypoint `scheduler.jobs`, new `filings` step, `DEPLOY_REMOTE` env for `publish.deploy`). Repo copied to `~/projects/sher_advisor_pipeline` on the Jetson (rsync, no .git), image built there; `--steps site` works (136 s). A one-off run of every step except deploy was started in the background, log `~/projects/sher_advisor_pipeline/run_test.log` (check memory and duration). Use `DEPLOY_KEY=/dev/null` for runs without deploy, otherwise compose creates a directory named `deploy_key`.
Done 2026-10-05: deploy key `~/projects/sher_advisor_pipeline/deploy_key` (GitHub deploy key `jetson`, write), weekly crontab entry (Sundays 02:00, flock), deploy-only run from the container pushed gh-pages (af6e0c2). Compose resolves `../deploy_key` relative to `scheduler/` (a wrong relative path makes Docker create a root-owned directory in its place). A full one-off run of every step except deploy took ~2h05m: prices 12.5 min, sec_facts 19.5, filings 35, financials 1, factors 47, scoring 14 s, model 3, research 3, intraday 1.6, site 2.5; no tracebacks (~720 'skipping/no data' lines for ex-members without CIK or prices). The first scheduled run, Sunday 2026-10-11 02:00, is the first time deploy runs after a full build on the Jetson; check `~/projects/sher_advisor_pipeline/run.log` afterwards.

## Motley Fool reverse engineering (`fool/`, built 2026-10-06)

Goal: learn what Fool Stock Advisor picks look like at the pick date, vs alternatives. Data in `advisor/fool/` (see `fool/README.md`, report `docs/fool_research.md`): `recs.parquet` (707 rows, 569 BUY, merged from nimar/fool_simulation CSV 2014-2025 and kupietools xlsx 2002-2020; 135 match exactly), `prices.parquet` (357/376 symbols: yfinance + Tiingo for delisted; key `TIINGO_API_KEY` in `.env`, free tier ~50 requests/hour, caches in `fool/raw/tiingo/`), `train.parquet` (569 picks + 5,690 date-matched lake controls, PIT features), `ciks.parquet`. TraderHQ and the Penn State paper give only aggregates; not ingested.
Findings: picks are persistent winners (median 36m return +81% vs +40% for controls), volatile, tech/consumer/communication; 365d median excess -3%, only 47% beat SPY, top 10 picks = 63% of Fool's own positive return. Outcome among picks is not predictable (AUC 0.46); selection is moderately predictable: LightGBM on price + SIC industry, time split (train <=2016, val 2017-2020, test 2021+) test AUC 0.729, PR-AUC 0.223 (random 0.08), 30% of picks in the top 10% of a date's cohort. At the real base rate (~2 picks/month in ~5,000 stocks) that is a shortlist filter, not a prediction. Fundamentals add nothing reliable (complete-case AUC ~0.6, n=79 picks); they exist for only ~32% of picks because SEC structured data starts ~2009-2011.
Pitfalls found: `quant/factors.py` values with a split-adjusted close against as-reported EPS/shares, so pe/ps/pb/fcf_yield (and the `value` score, `app_*`) are wrong for any stock that split later (AAPL 2019-11-29: 5.6 vs 22.5 correct); `fool/pit.py` does it right with `raw_close = close * later splits`, quant/ is NOT fixed (needs a decision). Controls are survivors (lake universe), so their forward returns are biased up; use controls for selection only. Control group is only the lake's ~600 symbols.

### Unfinished (resume here)
- Tiingo split refetch for delisted picks (~77 symbols, hourly cap): started in background, may not have finished. Rerun `python -m fool.prices` (everything cached, resumes), then `python -m fool.features`, `python -m fool.classifier`, `python -m fool.report`. Until then `fool.pit` leaves valuation NaN for those names on purpose. Remaining unresolved price symbols are listed in `fool/README.md`.
- Finish training: add a prior-pick feature (35% of BUYs repeat an earlier pick; reported separately since it is habit, not criteria), evaluate on the whole lake universe per month with top-20/top-50 hit rate, per-analyst models (David vs Tom), then pick the final model and save it. Text/news features are the only route to the "why".
- Decide whether to fix `quant/factors.py` splits.

## Next action

Decide on item 5 (ML has no skill) and whether to add a filings step to the scheduler. The scheduler now runs membership, sec_facts and deploy steps; nothing
schedules it (user runs it manually).

## Log

- 2026-10-06: added the Motley Fool module (`fool/`).
- 2026-10-05: created this file; items 1-3 committed; real run over the lake done (item 8 data, item 5 re-measured).
