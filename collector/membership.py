"""Point-in-time S&P 500 membership from fja05680/sp500 (MIT), kept as one row per membership
spell in advisor/membership/membership.parquet: symbol, start, end (end is NaT while still a member).

Today's constituents are a survivorship-biased universe: they include every stock that joined
the index after a run-up and exclude every one that fell out. Filtering each month's candidates to
the symbols that were members *then* removes the first effect. The second needs data for delisted
symbols, which is only partly available (`--backfill-list` shows what is missing).

Usage:
    python -m collector.membership                  # download and store
    python -m collector.membership --backfill-list  # removed-since-MIN_YEAR symbols with no data in the lake
"""
import argparse
import io
import urllib.request

import pandas as pd

from collector.store import DATA_DIR, source_symbols

URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
PATH = DATA_DIR / "membership" / "membership.parquet"
MIN_YEAR = 2009  # prices from yfinance start around here


def read_membership() -> pd.DataFrame:
    return pd.read_parquet(PATH)


def fetch() -> pd.DataFrame:
    with urllib.request.urlopen(URL, timeout=30) as response:
        raw = pd.read_csv(io.BytesIO(response.read()), parse_dates=["start_date", "end_date"])
    return raw.rename(columns={"ticker": "symbol", "start_date": "start", "end_date": "end"})


def filter_members(df: pd.DataFrame) -> pd.DataFrame:
    """Rows of a (symbol, as_of) frame whose symbol was an index member on that as_of date.
    Without a stored membership file every row is kept."""
    try:
        spells = read_membership()
    except FileNotFoundError:
        return df
    joined = df.assign(row=range(len(df))).merge(spells, on="symbol", how="left")
    inside = (joined["start"] <= joined["as_of"]) & (joined["end"].isna() | (joined["as_of"] < joined["end"]))
    return df.iloc[sorted(joined.loc[inside, "row"].unique())]


def member_counts(as_of_dates: pd.DatetimeIndex) -> pd.Series:
    spells = read_membership()
    return pd.Series(
        {d: int(((spells["start"] <= d) & (spells["end"].isna() | (d < spells["end"]))).sum()) for d in as_of_dates}
    )


def backfill_symbols() -> list[str]:
    spells = read_membership()
    removed = spells[spells["end"] >= pd.Timestamp(MIN_YEAR, 1, 1)]["symbol"]
    return sorted(set(removed) - set(source_symbols()))


def tracked_symbols() -> list[str]:
    """Lake symbols plus the delisted ex-members worth trying to fetch."""
    try:
        return sorted(set(source_symbols()) | set(backfill_symbols()))
    except FileNotFoundError:
        return source_symbols()


def run():
    spells = fetch()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    spells.to_parquet(PATH, index=False)
    print(f"[membership] {len(spells)} spells, {spells['symbol'].nunique()} symbols -> {PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-list", action="store_true")
    if parser.parse_args().backfill_list:
        print("\n".join(backfill_symbols()))
    else:
        run()
