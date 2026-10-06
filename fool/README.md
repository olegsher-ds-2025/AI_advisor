# fool

Motley Fool Stock Advisor recommendation history, for reverse-engineering what the picks have in common.

```bash
python -m fool.ingest    # download + clean both sources -> advisor/fool/{newrecs,picks_returns}.parquet
python -m fool.prices    # yfinance prices for every picked symbol + SPY -> advisor/fool/prices.parquet
python -m fool.combine   # merge + forward returns -> advisor/fool/recs.parquet   (use this for ML)
python -m fool.sec       # CIK + SIC for picked names (delisted ones by company name); SEC facts for them -> advisor/facts_extra
python -m fool.features  # picks + matched controls + point-in-time features -> advisor/fool/train.parquet
python -m fool.classifier  # recommended-or-not model: time split, logistic vs LightGBM, feature-set comparison
python -m fool.baseline  # walk-forward LightGBM sanity check (selection + outcome)
python -m fool.rank_check  # where our own scores/ml_scores rank Fool's picks at the pick date
python -m fool.report    # research report -> docs/fool_research.md
```

Sources: `nimar/fool_simulation` newrecs.csv (2014-2025, BUY/SELL/HOLD/REDUCE, parsed from Fool's PDF) and
`kupietools/Motley-Fool-recommendations-performance-analyzer` xlsx (2002-2020 BUYs with Fool's own returns). TraderHQ publishes aggregates only
and the Penn State paper's pick list is not public, so neither is ingested; use their totals (526 picks, 66% winners) as sanity targets.

## `recs.parquet`

Grain `(rec_date, symbol, action)`, 707 rows (569 BUY). `symbol` is today's ticker, `ticker_at_rec` the one Fool published.
`source` is `both` (135, same date + company in both files), `xlsx` or `newrecs`.

- `mf_*`: Fool's own return, S&P return and excess, as of `mf_return_end` (the xlsx snapshot, 2020-04-08, or `closed_date`). Only xlsx rows.
- `ret_{30,90,180,365}d`, `spy_*`, `excess_*`: our adj-close forward returns from `entry_date` (first trading day >= `rec_date`). NaN when the horizon
  hasn't elapsed or the symbol has no price history. **Use these as ML labels**; they are consistent across all years.
- `buy_number` / `is_repeat`: nth BUY of that symbol.

## Verification and known gaps

- Overlap 2014-03..2020-03: 135 BUYs match exactly on date; 15 don't (spin-offs like PYPL, picks listed in only one source, delisted names). Ticker
  renames are mapped in `combine.ALIASES`; the PDF parser's wrong symbols in `NEWRECS_FIXES`.
- Fool's returns vs ours (to 2020-04-08, 202 picks): correlation 0.98, but only ~40% within 10 pts. Fool's entry price and corporate-action adjustment differ, so
  `rec_price` is not comparable to market closes. The S&P column matches SPY to a 0.3-pt median error, which is how the snapshot date was inferred.
- **Survivorship bias**: yfinance has no history for 96 of 376 symbols (acquired, bankrupt or renamed), so 154 of 569 BUYs, mostly 2002-2010, have no
  `ret_*`. For those, `mf_return` is the only outcome. Don't treat the labelled set as unbiased; Fool's wins that got acquired are over-represented in the gap.
- 2020-2025 picks have no `mf_*` returns (the xlsx ends 2020-03).
- Some `newrecs` names are truncated ("Gate Entertai…").

## `train.parquet` (ML table)

One row per Fool BUY (`is_pick=1`, 569) plus 10 random lake-universe controls per pick on the same `rec_date` (`is_pick=0`, seed 7; never a symbol picked that day).
All features use data on or before `rec_date`; fundamentals come from `advisor/metrics` rows with `as_of` strictly earlier (at most 62 days stale).

- `PRICE_FEATURES` (momentum 1m-36m, 200d gap, 60d vol, 252d drawdown, distance from 52w low, SPY-relative momentum) exist for every row with 252+ bars of history.
  This is the fair feature set.
- `FUNDAMENTALS` exist for far fewer picks than controls (delisted names have no SEC facts in the lake), so NaN-ness itself separates the groups. Only compare
  models on fundamentals using rows where both are present.
- `PICK_ONLY` (`team`, `is_repeat`, `buy_number`, `source`, `mf_return`) are NaN for controls; never use them in the selection task.
- Targets: `ret_*`/`excess_*` for 30-365d and `beat_spy_365d`. **Control forward returns are survivors** (the lake universe is today's stocks), so control labels are biased
  up; use controls for selection only, and compare outcomes among picks.
- Splits: expanding window by `year`; for 365d labels embargo training rows whose `rec_date` is within 365 days of the test year (`fool.baseline` does this).

Baseline (6259 rows, 2008-2025 walk-forward): selection AUC 0.72 on price features (18/18 years above 0.5; strongest signals are 36m return,
sector, volatility), outcome AUC 0.46 among picks, i.e. no skill predicting which picks beat SPY from price features.

`app_*` columns are our own Stock Advisor ranking (`advisor/scores` category scores and total, plus cross-sectional percentiles of `total` and `ml_score`)
as of the last month-end before `rec_date`. They exist only for lake symbols with fundamentals (214 picks), so treat them as an evaluation of our ranking
and not as selection features. `python -m fool.rank_check` summarizes them.

Price coverage: 357 of 376 symbols (yfinance + Tiingo for delisted names). Still missing: AXYS BBBB CDWC DBTK ERJ GLYT GPS JW-A LCAV OMTR POSS PPDI PSTG PSUNQ RBK SE- SHFL TOMOY VTIV.

## Point-in-time features (`fool/pit.py`)

Fundamentals are rebuilt as of each `rec_date` from `advisor/financials` using only filings with `filed < rec_date`, valued at the **unadjusted** price of that
day: `raw_close = close * product(split ratios after that day)`. Splits come from `splits.parquet` / `splits_lake.parquet` (yfinance, Tiingo). Delisted names
priced from Tiingo return NaN valuation until their split history has been fetched (`tiingo_unverified`), instead of assuming "no splits".
Industry is the SEC SIC code (`sic2`, `sic3`), not today's yfinance sector.

Checked on AAPL 2019-11-29: raw close 267.25, market cap $1.19T, P/E 22.5. `advisor/metrics` shows P/E 5.6 for the same date because `quant/factors.py` divides a
split-adjusted close by as-reported EPS; it affects `pe`, `ps`, `pb`, `fcf_yield` and the `value` score of every stock that split later (not fixed there).

SEC structured facts start around 2009-2011, so any pick or control before that has no fundamentals however good the matching; that is why fundamentals are present
for only ~32% of picks and ~47% of controls.

## Classifier (`fool/classifier.py`)

y = `is_pick`. Split by `year`: train <= 2016, validation 2017-2020, test 2021+. Metrics: ROC-AUC, PR-AUC (base rate ~8%), and recall of true picks in the
top 10% of each date's cohort (random = 10%). Proposed model: LightGBM on price features + SIC industry; logistic regression is the baseline.
