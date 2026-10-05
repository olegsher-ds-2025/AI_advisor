"""Parquet storage in a Hive layout: <dataset>/symbol=<TICKER>/<dataset>.parquet"""
import html
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SOURCE_DIR = Path(os.environ.get("STOCK_MARKET_DIR", "~/jetson_mount/stock_market")).expanduser()
DATA_DIR = Path(os.environ.get("ADVISOR_DATA_DIR", SOURCE_DIR / "advisor")).expanduser()


def symbol_path(root: Path, dataset: str, symbol: str, filename: str) -> Path:
    return root / dataset / f"symbol={symbol}" / filename


def source_symbols() -> list[str]:
    return sorted(p.name.removeprefix("symbol=") for p in (SOURCE_DIR / "fundamentals").glob("symbol=*"))


def read_facts(symbol: str) -> pd.DataFrame | None:
    path = symbol_path(SOURCE_DIR, "fundamentals", symbol, "facts.parquet")
    return pd.read_parquet(path) if path.exists() else None


def read_symbol(dataset: str, symbol: str) -> pd.DataFrame | None:
    path = symbol_path(DATA_DIR, dataset, symbol, f"{dataset}.parquet")
    return pd.read_parquet(path) if path.exists() else None


def list_symbols(dataset: str) -> list[str]:
    return sorted(p.name.removeprefix("symbol=") for p in (DATA_DIR / dataset).glob("symbol=*"))


def upsert_symbol(dataset: str, symbol: str, df: pd.DataFrame, keys: list[str]) -> Path:
    path = symbol_path(DATA_DIR, dataset, symbol, f"{dataset}.parquet")
    if path.exists():
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
    df = df.drop_duplicates(keys, keep="last").sort_values(keys, ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return path


NEWS_PREFIX = re.compile(r"^\{[^}]*\}!?")
NEWS_SENTIMENT = re.compile(r"K:(-?\d+(?:\.\d+)?)")


def clean_news(news: pd.DataFrame) -> pd.DataFrame:
    """IB_NEWS headlines start with a `{A:..:K:<sentiment>:C:<confidence>}` tag (usually followed by `!`); split it off into `sentiment`
    (NaN when the provider gave none), unescape HTML and drop empty headlines."""
    tag = news["headline"].str.extract(NEWS_SENTIMENT)[0].astype(float)
    headline = news["headline"].str.replace(NEWS_PREFIX, "", regex=True).map(html.unescape).str.strip()
    return news.assign(headline=headline, sentiment=tag)[headline != ""]


def read_news(symbol: str, days: int = 30) -> pd.DataFrame:
    """Cleaned headlines of the last `days` daily partitions (not calendar days; partitions skip non-trading days)."""
    partitions = sorted((SOURCE_DIR / "news").glob("date=*"))[-days:]
    frames = [pd.read_parquet(p / "items.parquet", filters=[("symbol", "==", symbol)]) for p in partitions]
    return clean_news(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame(columns=["published_at", "headline", "sentiment"])


def read_all_news() -> pd.DataFrame:
    frames = [pd.read_parquet(p / "items.parquet") for p in sorted((SOURCE_DIR / "news").glob("date=*"))]
    return clean_news(pd.concat(frames, ignore_index=True)).sort_values("published_at")
