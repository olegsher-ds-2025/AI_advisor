# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Sher Stock Advisor AI: a personal stock-research system, not a trading bot. It
screens ~5,000 US stocks down to a shortlist via fundamentals, scores and
backtests them, and uses a local LLM to generate research notes (thesis, bull
case, bear case, risks). The human always makes the final call — the system
produces scores and explanations, never buy/sell signals.

The original design conversation is in `link.txt` (a shared ChatGPT link) — read
it for the full rationale behind architecture choices if something here seems
underspecified.

## Current state: V1.x

`collector/` (incl. intraday), `quant/` (incl. `indicators.py`), `ai/research.py`, `dashboard/`, `publish/`
and `scheduler/` are implemented and tested. `assistant/` (Open WebUI chat endpoint) is implemented. Not built: `ai/rag.py`. Each package README says what exists.

There is no database server. All storage is parquet (the Jetson works with
parquet), in a Hive layout: `<dataset>/symbol=<TICKER>/<dataset>.parquet`.

## Commands

```bash
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate

python -m collector.sec_facts [TICKER ...]            # SEC companyfacts: OCF/capex/gross profit/op income -> advisor/facts_extra/
python -m collector.financials TICKER [TICKER ...]    # fundamentals/ + facts_extra/ -> advisor/financials/
python -m collector.market TICKER [...] --period 5y   # yfinance prices -> advisor/prices/

python -m quant.factors [TICKER ...]                  # financials + prices -> advisor/metrics/
python -m quant.scoring                               # metrics -> advisor/scores/
python -m quant.model                                 # walk-forward LightGBM -> advisor/ml_scores/
python -m quant.backtest --score total ml_score       # top-N backtest vs SPY/QQQ
python -m collector.universe                          # quote type/sector -> advisor/universe/
python -m ai.research --top 10                        # LLM notes via the Jetson
python -m collector.intraday TICKER [...]            # 1-60 min bars -> advisor/intraday_<interval>/
python -m publish.build                               # static GitHub Pages site -> build/site/
streamlit run dashboard/app.py
python -m scheduler.jobs                              # whole daily pipeline

pytest tests/
```

Paths come from `.env` (see `.env.example`): `STOCK_MARKET_DIR` is the existing
lake (default `~/jetson_mount/stock_market`, a mount of the Jetson's storage;
treat it as read-only source data) and `ADVISOR_DATA_DIR` is where this project
writes (default `$STOCK_MARKET_DIR/advisor`). Point `ADVISOR_DATA_DIR` at a temp
dir for dry runs.

## Architecture

```
SEC facts parquet (fundamentals/) + yfinance -> collector/ -> advisor/*.parquet
    -> (not yet) quant/ factors+scoring
    -> (not yet) ai/ research+RAG (Jetson/Qwen)
    -> (not yet) dashboard/ (Streamlit)
```

- `collector/financials.py` — does not hit SEC. It reads the long-format facts
  already collected in `fundamentals/symbol=X/facts.parquet` (concept, value,
  unit, period_start, period_end, form, filed_at, accession_no) and pivots them
  to one wide row per (period, period_type, accn). `period_type` is `FY` for
  10-K/10-K/A and `Q` for 10-Q/10-Q/A. Flow facts are kept only when their
  duration is ~90 days (Q) or ~365 days (FY), because a 10-Q also reports 6M/9M
  YTD values for the same period end. The first concept in `CONCEPT_MAP` order
  wins per column.
- `collector/market.py` — pulls daily OHLCV via `yfinance` into `prices`.
- `collector/store.py` — path config plus `upsert_symbol()`: merges new rows into
  the symbol's parquet on the given keys (last wins), writes via temp file +
  rename.
- The existing `fundamentals/` only carries 10 concepts (revenue, net income,
  EPS, assets, liabilities, cash, equity, shares, long-term debt). Gross profit,
  operating income, operating cash flow and capex come from `collector/sec_facts.py`
  (SEC companyfacts, same long format, stored in `advisor/facts_extra/` and merged by
  `collector.financials`). Without that step they are NaN, and so is `free_cash_flow`.
- `financials` also derives discrete quarters from cumulative facts (Q2 = 6M-3M,
  Q3 = 9M-6M, Q4 = FY-9M) as extra `Q` rows, filed with the later input; `quant/factors.py`
  sums four of them for TTM.

## Infra split (per the original plan, not all built yet)

- **PC** (this machine): Python, data processing, backtesting, research notebooks.
- **Jetson Orin Nano (10.0.0.20)**: llama.cpp + Qwen inference, invoked by `ai/`
  once it exists. Its storage is mounted at `~/jetson_mount`, which is where the
  parquet lake lives.
- **Open WebUI**: eventual natural-language frontend over `metrics`/`scores`
  (parquet datasets that don't exist yet).

## Data model notes

- `financials` grain is (symbol, period, period_type, accn) — `period` is the
  period-end date and `filed` is the filing date. One period appears once per
  filing that reports it, so restatements are kept; a later filing's prior-period
  comparatives produce sparse rows. A symbol can have both `FY` and `Q` rows for
  the same period end — this is expected, not a bug.
- Planned but not yet created: `metrics` (computed factors), `scores`
  (quality/growth/value/momentum/risk/total), `research` (LLM output),
  `watchlist`, each as its own parquet dataset under `ADVISOR_DATA_DIR`.
- Any backtest or ML work on `financials`/`metrics` must respect point-in-time
  availability (use `filed`, not `period`, as the cutoff) — the original plan
  calls this out explicitly as a leakage risk to avoid.
