# Sher Stock Advisor AI

A personal, locally-run stock research system: screen ~5,000 US stocks down to a
shortlist using fundamentals, score and backtest the result, then use a local LLM
(Qwen on a Jetson) to generate research notes. This is a research tool, not a
trading bot — it produces scores and explanations, the human makes the call.

Origin: `link.txt` holds the ChatGPT conversation that specced this out.

## Status: V1.x (as of 2026-10-04)

Implemented, all on parquet with no database server:

- `collector/` - point-in-time financials from the existing SEC facts, yfinance prices, universe metadata.
- `quant/` - 18 point-in-time factors, stage-1 percentile scores, walk-forward LightGBM, backtest vs SPY/QQQ.
- `ai/research.py` - research notes from the Jetson llama.cpp server.
- `dashboard/` - Streamlit lists and company drill-down.
- `scheduler/` - daily pipeline (cron line in the module docstring, not installed).

Not built: `ai/rag.py`, sector-ETF benchmarks, TTM/FCF factors, transaction costs, a backtest before
2021 (prices cover 5 years).

Known limits: the universe is today's constituents (survivorship bias), the ML score shows no
out-of-sample skill (rank IC ~0.005), and the Qwen notes can misread scores, so check them against
the numbers. Source fundamentals lack shares/debt/revenue for some symbols.

## Quickstart

```bash
cp .env.example .env   # set STOCK_MARKET_DIR if the lake isn't at ~/jetson_mount/stock_market
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate

python -m collector.financials AAPL MSFT NVDA   # fundamentals/ facts -> advisor/financials/
python -m collector.market AAPL MSFT NVDA       # daily prices from yfinance -> advisor/prices/
python -m scheduler.jobs                        # factors, scores, ML scores, research notes
streamlit run dashboard/app.py
```

Run tests with `pytest tests/`.
