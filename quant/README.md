# quant/

Implemented: `factors.py`, stage-1 `scoring.py`, stage-2 `model.py`, `backtest.py`.

- `factors.py` - 22 point-in-time factors per symbol at each month-end (plus the latest
  bar) from `advisor/financials` + `advisor/prices` into `advisor/metrics/`. Filings count
  only once `filed` is before the as-of date. Growth, ROE/ROA and P/E use annual (FY)
  figures; gross/operating/FCF margin and FCF yield use TTM, the sum of the last four
  discrete quarters (`financials` derives Q2-Q4 from cumulative facts). Banks have no
  gross profit, so those factors are NaN for them. Missing: EBITDA and beta.
- `scoring.py` - stage 1: per-date cross-sectional percentile ranks averaged into
  quality/growth/value/momentum/risk scores (0-100) and a total, into `advisor/scores/`.
- `model.py` - stage 2: LightGBM walk-forward predicting 12-month forward excess return
  (vs the universe median) from ranked factors, into `advisor/ml_scores/`. A month's model
  trains only on months whose 12-month outcome was already realized by then.
- `backtest.py` - monthly rebalance, top-N equal weight by any score column vs SPY, QQQ and
  the equal-weighted universe: CAGR, volatility, max drawdown, Sharpe, Sortino, win rate
  vs SPY, turnover. Returns are net of `--cost-bps` (default 10) per unit of traded weight.
  A sector-matched benchmark holds each pick's SPDR sector ETF (needs ETF prices and
  `advisor/universe/` sectors; skipped otherwise). The history starts where prices start:
  run `collector.market --period max` for a longer window.

Known limits: the universe is today's constituents (survivorship bias flatters every
result), and ETFs are excluded via `advisor/universe/` (`python -m collector.universe`).
