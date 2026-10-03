"""Parquet storage in a Hive layout: <dataset>/symbol=<TICKER>/<dataset>.parquet"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SOURCE_DIR = Path(os.environ.get("STOCK_MARKET_DIR", "~/jetson_mount/stock_market")).expanduser()
DATA_DIR = Path(os.environ.get("ADVISOR_DATA_DIR", SOURCE_DIR / "advisor")).expanduser()


def symbol_path(root: Path, dataset: str, symbol: str, filename: str) -> Path:
    return root / dataset / f"symbol={symbol}" / filename


def read_facts(symbol: str) -> pd.DataFrame | None:
    path = symbol_path(SOURCE_DIR, "fundamentals", symbol, "facts.parquet")
    return pd.read_parquet(path) if path.exists() else None


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
