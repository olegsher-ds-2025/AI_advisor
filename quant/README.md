# quant/

Implemented: `factors.py`, stage-1 `scoring.py`, stage-2 `model.py`, `backtest.py`.

- `factors.py` - 18 point-in-time factors per symbol at each month-end (plus the latest
  bar) from `advisor/financials` + `advisor/prices` into `advisor/metrics/`. Filings count
  only once `filed` is before the as-of date. Income-statement ratios use annual (FY)
  figures; TTM needs Q4 derived as FY minus 9M, which `financials` doesn't carry yet.
  Missing: free-cash-flow margin, gross margin, EBITDA and beta (no source data yet).
- `scoring.py` - stage 1: per-date cross-sectional percentile ranks averaged into
  quality/growth/value/momentum/risk scores (0-100) and a total, into `advisor/scores/`.
- `model.py` - stage 2: LightGBM walk-forward predicting 12-month forward excess return
  (vs the universe median) from ranked factors, into `advisor/ml_scores/`. A month's model
  trains only on months whose 12-month outcome was already realized by then.
- `backtest.py` - monthly rebalance, top-N equal weight by any score column vs SPY, QQQ and
  the equal-weighted universe: CAGR, volatility, max drawdown, Sharpe, Sortino, win rate
  vs SPY, turnover. No transaction costs. Sector ETFs and the 2015 start are not done:
  prices cover 5 years (`collector.market --period max` would extend them).

Known limits: the universe is today's constituents (survivorship bias flatters every
result), and ETFs are excluded via `advisor/universe/` (`python -m collector.universe`).
