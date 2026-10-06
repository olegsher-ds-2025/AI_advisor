"""Point-in-time fundamentals for (symbol, date) pairs: only filings made before the date, valued at the *unadjusted* price of that date.

yfinance/Tiingo-adjusted closes are split-adjusted to today while filings report shares and EPS as of their own date, so valuation needs
raw_close(t) = close(t) * product of split ratios after t. (advisor/metrics skips this step; its pe/ps/pb/fcf_yield are off by the factor for any stock that split later.)"""
import numpy as np
import pandas as pd

from collector.store import read_symbol
from fool.ingest import FOOL_DIR, RAW_DIR
from quant.factors import BALANCE_COLUMNS, fundamental_factors

TIINGO_DIR = RAW_DIR / "tiingo"
FUNDAMENTALS = ["net_margin", "roe", "roa", "revenue_growth", "net_income_growth", "eps_growth", "pe", "ps", "pb", "debt_to_equity",
                "liabilities_to_assets", "gross_margin", "operating_margin", "fcf_margin", "fcf_yield", "market_cap", "filing_age_days"]


def tiingo_unverified() -> set[str]:
    """Symbols priced from Tiingo whose split history hasn't been fetched yet: 'no splits' would be an assumption, so their valuation stays NaN."""
    cached = {p.stem for p in TIINGO_DIR.glob("*.parquet") if not p.stem.endswith("_splits")}
    return {s for s in cached if not (TIINGO_DIR / f"{s}_splits.parquet").exists()}


def load_splits() -> dict[str, pd.DataFrame]:
    frames = [pd.read_parquet(FOOL_DIR / n) for n in ("splits.parquet", "splits_lake.parquet") if (FOOL_DIR / n).exists()]
    splits = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"]).sort_values("date")
    return {s: g.set_index("date")["ratio"] for s, g in splits.groupby("symbol")}


def raw_close(px: pd.DataFrame, splits: dict[str, pd.Series], symbol: str, t: pd.Timestamp) -> float:
    i = px.index.searchsorted(t, side="right") - 1
    if i < 0 or t - px.index[i] > pd.Timedelta(days=5):
        return np.nan
    later = splits.get(symbol)
    factor = later[later.index > px.index[i]].prod() if later is not None else 1.0
    return px["close"].iloc[i] * factor


def fundamentals_asof(df: pd.DataFrame, series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """df needs rec_date, symbol (key of advisor/financials) and yf_symbol (key of series)."""
    splits, unverified = load_splits(), tiingo_unverified()
    fins: dict[str, pd.DataFrame | None] = {}
    rows = []
    for sym, yf_sym, t in zip(df["symbol"], df["yf_symbol"], df["rec_date"]):
        if sym not in fins:
            fins[sym] = read_symbol("financials", sym)
        fin, px = fins[sym], series.get(yf_sym)
        if fin is None or px is None or yf_sym in unverified:
            rows.append({}); continue
        close = raw_close(px, splits, yf_sym, t)
        known = fin[fin["filed"] < t]
        if known.empty or np.isnan(close):
            rows.append({}); continue
        f = fundamental_factors(fin, t, close)
        shares = known.sort_values(["period", "filed"]).groupby("period").last()[BALANCE_COLUMNS].ffill().iloc[-1]["shares"]
        f.update(market_cap=close * shares if pd.notna(shares) else np.nan, filing_age_days=(t - known["filed"].max()).days)
        rows.append(f)
    return pd.DataFrame(rows, index=df.index).reindex(columns=FUNDAMENTALS)
