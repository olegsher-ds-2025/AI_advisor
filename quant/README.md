# quant/ (not yet implemented)

Planned for V1.1-V1.3:

- `factors.py` - compute the ~40 factors (Quality/Growth/Value/Momentum/Risk) from
  `financials` + `prices` into the `metrics` table.
- `scoring.py` - two-stage scoring: per-category fundamental scores, then an
  XGBoost/LightGBM model trained on point-in-time features (no look-ahead leakage)
  to estimate 12-month forward excess return. Writes to `scores`.
- `backtest.py` - periodic rebalance backtest (2015-present) vs SPY/QQQ/sector ETFs,
  reporting CAGR, volatility, max drawdown, Sharpe, Sortino, win rate, turnover.

Requires the `metrics` and `scores` tables, which don't exist yet - add them in a
migration under `database/migrations/` before writing this code.
