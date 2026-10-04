# Dashboard

Two front ends read the same parquet data:

- `dashboard/app.py`: Streamlit, local deep-dives (`streamlit run dashboard/app.py`).
- `publish/`: static site for GitHub Pages at https://stock_dashboard.sher.biz.

## Static site

`python -m publish.build` writes `build/site/`: `data/index.json` (scores table),
`data/symbols/<TICKER>.json` (1y closes, score history, factors, indicator snapshot, research
note) and the static front end in `publish/static/`. Only scores, prices, indicators and research
notes are published. Raw financials and news stay local.

Pages can't reach the parquet lake on the Jetson, so the site is built on this machine and
pushed to the `gh-pages` branch.

## Indicators

Price change, RSI(14), ATR(14), Alligator (13/8, 8/5, 5/3), Supertrend(10, 3) and IIX(21),
computed by `quant/indicators.py` per timeframe:

| Timeframe | Source |
|---|---|
| 1, 5, 15, 30, 60 min | yfinance intraday via `collector/intraday.py` |
| 120, 240, 480 min | resampled from 60 min bars, anchored at the 09:30 ET open |
| daily, weekly | `prices`; weekly resampled from daily |

yfinance caps intraday history (1m 7 days, 5/15/30m 60 days, 60m 730 days), so intraday is
collected daily for a watchlist (top scored equities, `--watchlist-top`) and accumulates over
time. Symbols outside the watchlist show daily and weekly only.
