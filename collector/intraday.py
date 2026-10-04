"""yfinance collector - intraday bars for a small watchlist, stored per interval.

yfinance caps history per interval (1m 7d, 5/15/30m 60d, 60m 730d). Bars are stored in
exchange time (naive, America/New_York) so 120/240/480 min bars can be resampled from 60m
anchored at the 09:30 open. Run it daily so the capped windows keep accumulating.

Usage:
    python -m collector.intraday AAPL MSFT NVDA
"""
import argparse

import pandas as pd
import yfinance as yf

from collector.store import upsert_symbol

INTERVAL_PERIODS = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "60m": "730d"}
EXCHANGE_TZ = "America/New_York"


def dataset(interval: str) -> str:
    return f"intraday_{interval}"


def run(tickers: list[str]):
    for ticker in tickers:
        ticker = ticker.upper()
        for interval, period in INTERVAL_PERIODS.items():
            hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False).dropna(subset=["Close"])
            if hist.empty:
                print(f"[intraday] {ticker} {interval}: no data returned")
                continue
            rows = pd.DataFrame(
                {
                    "symbol": ticker,
                    "ts": hist.index.tz_convert(EXCHANGE_TZ).tz_localize(None),
                    "open": hist["Open"].to_numpy(),
                    "high": hist["High"].to_numpy(),
                    "low": hist["Low"].to_numpy(),
                    "close": hist["Close"].to_numpy(),
                    "volume": hist["Volume"].fillna(0).astype("int64").to_numpy(),
                }
            )
            upsert_symbol(dataset(interval), ticker, rows, ["ts"])
            print(f"[intraday] {ticker} {interval}: {len(rows)} bars")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    run(parser.parse_args().tickers)
