# quant/

Implemented (V1.1): `factors.py` and stage-1 `scoring.py`. Planned: ML scoring and backtest.

- `factors.py` - 18 point-in-time factors per symbol at each month-end (plus the latest
  bar) from `advisor/financials` + `advisor/prices` into `advisor/metrics/`. Filings count
  only once `filed` is before the as-of date. Income-statement ratios use annual (FY)
  figures; TTM needs Q4 derived as FY minus 9M, which `financials` doesn't carry yet.
  Missing: free-cash-flow margin, gross margin, EBITDA and beta (no source data yet).
- `scoring.py` - stage 1: per-date cross-sectional percentile ranks averaged into
  quality/growth/value/momentum/risk scores (0-100) and a total, into `advisor/scores/`.
  Stage 2 (below) is not built.
- (planned) `scoring.py` stage 2 - XGBoost/LightGBM model trained on point-in-time features (no look-ahead leakage)
  to estimate 12-month forward excess return.
- `backtest.py` - periodic rebalance backtest (2015-present) vs SPY/QQQ/sector ETFs,
  reporting CAGR, volatility, max drawdown, Sharpe, Sortino, win rate, turnover.

Reads `advisor/financials/` and `advisor/prices/` and writes `advisor/metrics/` and
`advisor/scores/` as parquet (Hive layout, `symbol=<TICKER>/`).
