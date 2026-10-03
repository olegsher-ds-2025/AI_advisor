"""yfinance metadata per symbol (quote type, sector, industry), used to drop ETFs/funds from scoring.

Usage:
    python -m collector.universe            # every symbol in fundamentals/
    python -m collector.universe AAPL SPY
"""
import argparse

import pandas as pd
import yfinance as yf

from collector.store import DATA_DIR, source_symbols

PATH = DATA_DIR / "universe" / "universe.parquet"
FIELDS = {"quoteType": "quote_type", "sector": "sector", "industry": "industry", "longName": "name"}


def read_universe() -> pd.DataFrame:
    return pd.read_parquet(PATH)


def fetch(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info
    except Exception as exc:  # yfinance raises assorted HTTP/JSON errors for delisted symbols
        print(f"[universe] {symbol}: {exc}")
        info = {}
    return {"symbol": symbol, **{col: info.get(key) for key, col in FIELDS.items()}}


def run(symbols: list[str]):
    symbols = symbols or source_symbols()
    fresh = pd.DataFrame([fetch(s.upper()) for s in symbols])
    if PATH.exists():
        fresh = pd.concat([pd.read_parquet(PATH), fresh]).drop_duplicates("symbol", keep="last")
    PATH.parent.mkdir(parents=True, exist_ok=True)
    fresh.sort_values("symbol").to_parquet(PATH, index=False)
    print(f"[universe] {len(fresh)} symbols -> {PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    run(parser.parse_args().symbols)
