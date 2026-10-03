"""yfinance collector - historical daily prices.

Usage:
    python -m collector.market AAPL MSFT NVDA --period 5y
"""
import argparse

import pandas as pd
import yfinance as yf

from collector.store import upsert_symbol

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close"]


def run(tickers: list[str], period: str):
    for ticker in tickers:
        ticker = ticker.upper()
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=False)
        if hist.empty:
            print(f"[market] {ticker}: no data returned")
            continue
        hist = hist.dropna(subset=PRICE_COLUMNS)

        rows = pd.DataFrame(
            {
                "symbol": ticker,
                "date": hist.index.tz_localize(None).normalize(),
                "open": hist["Open"].to_numpy(),
                "high": hist["High"].to_numpy(),
                "low": hist["Low"].to_numpy(),
                "close": hist["Close"].to_numpy(),
                "adj_close": hist["Adj Close"].to_numpy(),
                "volume": hist["Volume"].fillna(0).astype("int64").to_numpy(),
            }
        )
        path = upsert_symbol("prices", ticker, rows, ["date"])
        print(f"[market] {ticker}: {len(rows)} daily bars -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--period", default="5y", help="yfinance period, e.g. 1y, 5y, max")
    args = parser.parse_args()
    run(args.tickers, args.period)
