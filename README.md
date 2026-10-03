# Sher Stock Advisor AI

A personal, locally-run stock research system: screen ~5,000 US stocks down to a
shortlist using fundamentals, score and backtest the result, then use a local LLM
(Qwen on a Jetson) to generate research notes. This is a research tool, not a
trading bot — it produces scores and explanations, the human makes the call.

Origin: `link.txt` holds the ChatGPT conversation that specced this out.

## Status: V1.0 (Data phase)

Implemented: SEC EDGAR + yfinance collectors writing into PostgreSQL.
Not yet implemented: factors/scoring/backtest (`quant/`), LLM research/RAG (`ai/`),
dashboard (`dashboard/`), daily pipeline (`scheduler/`) — see the README in each
for what's planned there.

## Quickstart

```bash
cp .env.example .env   # fill in SEC_USER_AGENT at minimum
docker compose up -d postgres
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate

python -m collector.sec AAPL MSFT NVDA      # fundamentals from SEC
python -m collector.market AAPL MSFT NVDA   # daily prices from yfinance
```

Run tests with `pytest tests/`.
