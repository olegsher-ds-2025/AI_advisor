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

## Current state: V1.0 (Data phase only)

Only `collector/` and `database/schema.sql` are implemented and tested. `quant/`,
`ai/`, `dashboard/`, `scheduler/` are stubs — each has a README describing what
it will do and what it depends on. Don't assume code exists there; check the
README first.

## Commands

```bash
docker compose up -d postgres        # start the DB (schema.sql auto-applies on first boot)
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate

python -m collector.sec TICKER [TICKER ...]      # SEC fundamentals -> companies, financials
python -m collector.market TICKER [...] --period 5y   # yfinance prices -> prices

pytest tests/
```

`SEC_USER_AGENT` must be set (SEC fair-access policy requires a contact string,
e.g. `"Name email@example.com"`) — see `.env.example`. If schema.sql changes
after the postgres volume already exists, it won't re-run automatically; drop
the volume (`docker compose down -v`) or apply the change manually with `psql`.

## Architecture

```
SEC EDGAR + yfinance -> collector/ -> PostgreSQL -> (not yet) quant/ factors+scoring
                                                   -> (not yet) ai/ research+RAG (Jetson/Qwen)
                                                   -> (not yet) dashboard/ (Streamlit)
```

- `collector/sec.py` — pulls XBRL company facts from `data.sec.gov` (no API key,
  but requires a `User-Agent`). Maps ticker -> CIK via
  `sec.gov/files/company_tickers.json` (an index->object dict, *not* the
  fields/data array format some other SEC endpoints use). One row per
  (ticker, period, period_type) in `financials`, where `period_type` is `FY`
  for 10-K facts and `Q` for 10-Q facts, derived from each XBRL fact's `form`
  field.
- `collector/market.py` — pulls daily OHLCV via `yfinance` into `prices`.
  Upserts a minimal placeholder row into `companies` first (`ON CONFLICT DO
  NOTHING`) since `prices.ticker` has an FK into `companies` and this collector
  may run before `collector.sec` has created the real row — don't let it clobber
  a name already set by `collector.sec`.
- `collector/db.py` — thin psycopg2 wrapper; `upsert()` is a generic
  `INSERT ... ON CONFLICT` for list-of-dict rows, used by both collectors.
- SEC rate limit: `collector/sec.py` sleeps 0.15s between tickers to stay under
  SEC's fair-access limit (~10 req/s). Don't remove this when batching many
  tickers.

## Infra split (per the original plan, not all built yet)

- **PC** (this machine): PostgreSQL, Python, data collection, backtesting,
  research notebooks.
- **Jetson Orin Nano (10.0.0.20)**: inference only — llama.cpp + Qwen, invoked by
  `ai/` once it exists. Don't put data processing or the DB there.
- **Open WebUI**: eventual natural-language frontend, translating questions like
  "companies with revenue growth >20% and FCF margin >15%" into SQL against
  `metrics`/`scores` (tables that don't exist yet).

## Data model notes

- `financials` grain is (ticker, period, period_type) — `period` is the XBRL
  fact's `end` date, not a filing date. A ticker can have both an `FY` and a `Q`
  row for overlapping end dates (10-K and 10-Q filings reporting the same
  period-end) — this is expected, not a bug.
- Planned but not yet created: `metrics` (computed factors), `scores`
  (quality/growth/value/momentum/risk/total), `research` (LLM output),
  `watchlist`. Add these as new files under `database/migrations/`, not by
  editing `schema.sql` in place, once `quant/` or `ai/` start needing them.
- Any backtest or ML work on `financials`/`metrics` must respect point-in-time
  availability (use `filed` date, not `period`/`end` date, as the cutoff) — the
  original plan calls this out explicitly as a leakage risk to avoid.
