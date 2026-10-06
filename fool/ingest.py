"""Motley Fool Stock Advisor recommendation history -> advisor/fool/*.parquet (flat, not per-symbol)."""
import re
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from collector.store import DATA_DIR

FOOL_DIR = DATA_DIR / "fool"
RAW_DIR = FOOL_DIR / "raw"
PRICES_PATH = FOOL_DIR / "prices.parquet"
SPLITS_PATH = FOOL_DIR / "splits.parquet"

CSV_URL = "https://raw.githubusercontent.com/nimar/fool_simulation/main/newrecs.csv"
XLSX_URL = "https://raw.githubusercontent.com/kupietools/Motley-Fool-recommendations-performance-analyzer/main/Motley%20Fool%20picks%20returns.xlsx"

CLOSED = re.compile(r"\s*\(Closed:\s*(\d{2}/\d{2}/\d{4})\)")
CORP_ACTION = re.compile(r"\s*Corporate Action Details$")
SYMBOL_FIXES = {"LIONS": "LGF.A"}  # PDF parser split "Lions Gate" into symbol "Lions"
DELISTED = re.compile(r"\.DL\d?$")
CAP_UNITS = {"M": 1e6, "B": 1e9, "T": 1e12}


def download(url: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / Path(urllib.parse.unquote(url)).name
    urllib.request.urlretrieve(url, path)
    return path


def parse_market_cap(value) -> float:
    m = re.fullmatch(r"\$([\d.]+)([MBT])", str(value))
    return float(m[1]) * CAP_UNITS[m[2]] if m else float("nan")


def clean_newrecs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%y")
    df["symbol"] = df["symbol"].str.strip().str.upper().replace(SYMBOL_FIXES)
    df["recommendation"] = df["recommendation"].str.strip().str.upper()
    df["name"] = df["name"].str.strip()
    return df.drop_duplicates(["date", "symbol", "recommendation"]).sort_values(["date", "symbol"], ignore_index=True)


def clean_picks(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Raw Data from MF (filter this!)")
    closed = raw["Company"].str.extract(CLOSED)[0]
    price = pd.to_numeric(raw["Adjusted Rec Price"], errors="coerce")
    ticker = raw["Ticker"].str.strip()
    df = pd.DataFrame({
        "rec_date": raw["Recommendation Date"],
        "company": raw["Company"].str.replace(CLOSED, "", regex=True).str.replace(CORP_ACTION, "", regex=True).str.strip(),
        "ticker_raw": ticker,
        "ticker": ticker.str.split().str[0].str.replace(DELISTED, "", regex=True),
        "delisted": ticker.str.contains(DELISTED),
        "closed_date": pd.to_datetime(closed, format="%m/%d/%Y"),
        "market_cap": raw["Market Cap"].map(parse_market_cap),
        "team": raw["Team"],
        "risk_rating": raw["Risk rating"],
        "rec_price": price,
        "return": raw["Return (keep sorted by this column!)"],
        "spx_return": raw["S&P Return, same period"],
        "excess_return": raw["Difference Vs. S&P Return"],
    })
    df["price_unavailable"] = price.isna()
    return df.sort_values(["rec_date", "ticker"], ignore_index=True)


def main() -> None:
    FOOL_DIR.mkdir(parents=True, exist_ok=True)
    recs = clean_newrecs(download(CSV_URL))
    picks = clean_picks(download(XLSX_URL))
    recs.to_parquet(FOOL_DIR / "newrecs.parquet", index=False)
    picks.to_parquet(FOOL_DIR / "picks_returns.parquet", index=False)
    print(f"newrecs: {len(recs)} rows {recs.date.min():%Y-%m-%d}..{recs.date.max():%Y-%m-%d}")
    print(f"picks_returns: {len(picks)} rows {picks.rec_date.min():%Y-%m-%d}..{picks.rec_date.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
