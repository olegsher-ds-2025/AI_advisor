"""yfinance collector - historical daily prices.

Usage:
    python -m collector.market AAPL MSFT NVDA --period 5y
"""
import argparse

import yfinance as yf

from collector.db import get_connection, upsert


PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close"]


def run(tickers: list[str], period: str):
    conn = get_connection()
    try:
        _run(conn, tickers, period)
    finally:
        conn.close()


def _run(conn, tickers: list[str], period: str):
    for ticker in tickers:
        ticker = ticker.upper()
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=False)
        if hist.empty:
            print(f"[market] {ticker}: no data returned")
            continue
        hist = hist.dropna(subset=PRICE_COLUMNS)
        hist["Volume"] = hist["Volume"].fillna(0)

        # prices.ticker has an FK to companies; make sure a row exists even if
        # collector.sec hasn't been run yet for this ticker.
        upsert(
            conn,
            "companies",
            [{"ticker": ticker, "name": ticker}],
            conflict_keys=["ticker"],
            on_conflict_do_nothing=True,
        )

        rows = [
            {
                "ticker": ticker,
                "date": idx.date().isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "adj_close": float(row["Adj Close"]),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]
        upsert(conn, "prices", rows, conflict_keys=["ticker", "date"])
        print(f"[market] {ticker}: upserted {len(rows)} daily bars")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--period", default="5y", help="yfinance period, e.g. 1y, 5y, max")
    args = parser.parse_args()
    run(args.tickers, args.period)
