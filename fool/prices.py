"""Daily prices (raw close + adj close) for every symbol Motley Fool picked, plus SPY -> advisor/fool/prices.parquet.

Kept separate from advisor/prices so the daily pipeline's universe isn't affected."""
import os
import time
import urllib.error
import urllib.request
import json

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from fool.combine import merge_sources
from fool.ingest import PRICES_PATH, RAW_DIR, SPLITS_PATH

load_dotenv()
TIINGO_URL = "https://api.tiingo.com/tiingo/daily/{}/prices?startDate=2001-01-01"
TIINGO_DIR = RAW_DIR / "tiingo"

BATCH = 50


def fetch(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for i in range(0, len(symbols), BATCH):
        raw = yf.download(symbols[i:i + BATCH], start="2001-01-01", auto_adjust=False, group_by="ticker", progress=False, threads=True)
        for sym in symbols[i:i + BATCH]:
            sub = raw[sym][["Close", "Adj Close"]].dropna() if sym in raw.columns.get_level_values(0) else pd.DataFrame()
            if not sub.empty:
                frames.append(pd.DataFrame({"symbol": sym, "date": sub.index.tz_localize(None).normalize(),
                                            "close": sub["Close"].to_numpy(), "adj_close": sub["Adj Close"].to_numpy()}))
    return pd.concat(frames, ignore_index=True)


def tiingo_get(ticker: str) -> list[dict]:
    req = urllib.request.Request(TIINGO_URL.format(ticker), headers={"Authorization": f"Token {os.environ['TIINGO_API_KEY']}"})
    while True:
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code != 429:
                raise
            print("tiingo rate limit, sleeping 10 min", flush=True)
            time.sleep(600)


def tiingo_frame(symbol: str, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Tiingo's close is unadjusted; back-adjust for splits only so it matches yfinance's Close
    after = df["splitFactor"][::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    date = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return pd.DataFrame({"symbol": symbol, "date": date, "close": df["close"] / after, "adj_close": df["adjClose"]}), \
        pd.DataFrame({"symbol": symbol, "date": date[df["splitFactor"] != 1], "ratio": df["splitFactor"][df["splitFactor"] != 1]})


def fill_from_tiingo(missing: dict[str, list[str]]) -> pd.DataFrame:
    """missing: yf_symbol -> candidate Tiingo tickers (historical tickers differ after renames); first with data wins, cached per symbol."""
    TIINGO_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for sym, candidates in missing.items():
        cache, splits_cache = TIINGO_DIR / f"{sym}.parquet", TIINGO_DIR / f"{sym}_splits.parquet"
        if not (cache.exists() and splits_cache.exists()):
            for cand in candidates:
                rows = tiingo_get(cand)
                if rows:
                    frame, splits = tiingo_frame(sym, rows)
                    frame.to_parquet(cache, index=False)
                    splits.to_parquet(splits_cache, index=False)
                    print(f"tiingo {sym} <- {cand}: {len(rows)} rows", flush=True)
                    break
            else:
                print(f"tiingo {sym}: not found ({candidates})", flush=True)
                continue
        frames.append(pd.read_parquet(cache))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_splits(symbols: list[str]) -> pd.DataFrame:
    """Split ratios (2.0 = 2-for-1) by ex-date: Tiingo caches for delisted names, yfinance for the rest. Needed to rebuild the unadjusted price on any past date."""
    frames = [pd.read_parquet(p) for p in TIINGO_DIR.glob("*_splits.parquet")]
    have = {f["symbol"].iloc[0] for f in frames if len(f)} | {p.name.removesuffix("_splits.parquet") for p in TIINGO_DIR.glob("*_splits.parquet")}
    for sym in symbols:
        if sym in have:
            continue
        s = yf.Ticker(sym).splits
        if s is not None and len(s):
            frames.append(pd.DataFrame({"symbol": sym, "date": s.index.tz_localize(None).normalize(), "ratio": s.to_numpy()}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["symbol", "date", "ratio"])


def main() -> None:
    recs = merge_sources()
    syms = sorted({*recs["yf_symbol"], "SPY"})
    df = fetch(syms)
    missing = sorted(set(syms) - set(df.symbol))
    cands = recs.assign(alt=recs["ticker_at_rec"].str.replace(".", "-", regex=False)).groupby("yf_symbol")["alt"].agg(lambda s: list(dict.fromkeys(s)))
    gap = {m: list(dict.fromkeys([m, *cands.get(m, [])])) for m in missing}
    df = pd.concat([df, fill_from_tiingo(gap)], ignore_index=True)
    df.to_parquet(PRICES_PATH, index=False)
    collect_splits(sorted(set(df.symbol) - {"SPY"})).to_parquet(SPLITS_PATH, index=False)
    still = sorted(set(syms) - set(df.symbol))
    print(f"prices: {df.symbol.nunique()}/{len(syms)} symbols, {len(df)} rows; still missing: {still}")


if __name__ == "__main__":
    main()
