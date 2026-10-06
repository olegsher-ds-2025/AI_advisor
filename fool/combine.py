"""Merge the xlsx (2002-2020 BUYs with Fool's own returns) and newrecs.csv (2014-2025 all actions) into advisor/fool/recs.parquet.

Grain: (rec_date, symbol, action). `symbol` is the current ticker, `ticker_at_rec` the one Fool published."""
import numpy as np
import pandas as pd

from fool.ingest import FOOL_DIR, PRICES_PATH

# historical ticker -> current ticker of the same company, so both sources key identically
ALIASES = {"FB": "META", "SQ": "XYZ", "WETF": "WT", "FEYE": "MNDT", "NCR": "VYX", "SPB": "JEF", "SINA": "WB", "GOOGL": "GOOG"}
# newrecs.csv symbols the PDF parser resolved to the wrong company
NEWRECS_FIXES = {(pd.Timestamp("2020-01-16"), "A"): "NICE"}
XLSX_SNAPSHOT = pd.Timestamp("2020-04-08")  # inferred: SPY return from rec_date to this day best matches the xlsx's S&P column
HORIZONS = {"30d": 30, "90d": 90, "180d": 180, "365d": 365}


def yf_symbol(symbol: pd.Series) -> pd.Series:
    return symbol.str.replace(".", "-", regex=False)


def merge_sources() -> pd.DataFrame:
    xlsx = pd.read_parquet(FOOL_DIR / "picks_returns.parquet")
    new = pd.read_parquet(FOOL_DIR / "newrecs.parquet")

    xlsx = xlsx.assign(rec_date=xlsx["rec_date"], action="BUY", symbol=xlsx["ticker"].replace(ALIASES), ticker_at_rec=xlsx["ticker"])
    fixed = [NEWRECS_FIXES.get((d, s), s) for d, s in zip(new["date"], new["symbol"])]
    new = new.assign(symbol=pd.Series(fixed).replace(ALIASES), action=new["recommendation"]).rename(columns={"date": "rec_date", "name": "name_newrecs"})

    keys = ["rec_date", "symbol", "action"]
    xlsx = xlsx.drop_duplicates(keys)
    df = xlsx.merge(new[keys + ["name_newrecs"]], on=keys, how="outer", indicator="source")
    df["source"] = df["source"].map({"left_only": "xlsx", "right_only": "newrecs", "both": "both"}).astype(str)
    df["company"] = df["company"].fillna(df["name_newrecs"])
    df["ticker_at_rec"] = df["ticker_at_rec"].fillna(df["symbol"])
    df["yf_symbol"] = yf_symbol(df["symbol"])
    df = df.drop(columns=["ticker", "ticker_raw", "name_newrecs"]).sort_values(keys, ignore_index=True)

    df["mf_return_end"] = df["closed_date"].fillna(XLSX_SNAPSHOT).where(df["return"].notna())
    df = df.rename(columns={"return": "mf_return", "spx_return": "mf_spx_return", "excess_return": "mf_excess_return"})
    df["buy_number"] = df["action"].eq("BUY").groupby(df["symbol"]).cumsum().where(df["action"].eq("BUY"))
    df["is_repeat"] = df["buy_number"].gt(1)
    return df


def load_fool_series() -> dict[str, pd.DataFrame]:
    prices = pd.read_parquet(PRICES_PATH)
    return {s: g.set_index("date").sort_index() for s, g in prices.groupby("symbol")}


def add_forward_returns(df: pd.DataFrame, series: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    series = series or load_fool_series()
    spy = series["SPY"]["adj_close"]

    def entry_and_forward(sym: str, date: pd.Timestamp) -> dict:
        out = {"entry_date": pd.NaT, "entry_close": np.nan, "entry_adj": np.nan}
        for h in HORIZONS:
            out[f"ret_{h}"] = out[f"spy_{h}"] = np.nan
        px = series.get(sym)
        if px is None or px.index[-1] < date:
            return out
        i = px.index.searchsorted(date)
        if px.index[i] - date > pd.Timedelta(days=5):
            return out
        out.update(entry_date=px.index[i], entry_close=px["close"].iloc[i], entry_adj=px["adj_close"].iloc[i])
        for h, days in HORIZONS.items():
            target = date + pd.Timedelta(days=days)
            j = px.index.searchsorted(target)
            if j >= len(px) or px.index[j] - target > pd.Timedelta(days=5):
                continue
            out[f"ret_{h}"] = px["adj_close"].iloc[j] / out["entry_adj"] - 1
            k, m = spy.index.searchsorted(px.index[i]), spy.index.searchsorted(px.index[j])
            out[f"spy_{h}"] = spy.iloc[m] / spy.iloc[k] - 1
        return out

    fwd = pd.DataFrame([entry_and_forward(s, d) for s, d in zip(df["yf_symbol"], df["rec_date"])], index=df.index)
    for h in HORIZONS:
        fwd[f"excess_{h}"] = fwd[f"ret_{h}"] - fwd[f"spy_{h}"]
    return pd.concat([df, fwd], axis=1)


def main() -> None:
    df = add_forward_returns(merge_sources())
    df.to_parquet(FOOL_DIR / "recs.parquet", index=False)
    print(df["source"].value_counts().to_dict(), len(df))


if __name__ == "__main__":
    main()
