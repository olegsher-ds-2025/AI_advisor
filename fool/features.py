"""Training table: Fool BUYs (is_pick=1) plus date-matched random controls from the lake universe (is_pick=0) -> advisor/fool/train.parquet.

Two tasks share it: *selection* (is_pick from features; no forward data involved) and *outcome* (excess_* among picks).
Every feature is computed from data on or before `rec_date`; fundamentals come from advisor/metrics rows whose `as_of` is strictly earlier."""
import numpy as np
import pandas as pd

from collector.store import DATA_DIR, list_symbols, read_symbol
from fool.combine import add_forward_returns, load_fool_series
from fool.ingest import FOOL_DIR
from fool.pit import FUNDAMENTALS, fundamentals_asof
from fool.sec import CIKS_PATH, lake_meta

SEED = 7
CONTROLS_PER_PICK = 10
MIN_HISTORY = 252
PRICE_FEATURES = ["ret_1m", "ret_3m", "ret_6m", "ret_12m_ex_1m", "ret_36m", "sma200_gap", "vol_60d", "drawdown_252d", "from_52w_low",
                  "rel_ret_3m", "rel_ret_12m_ex_1m"]
APP_SCORES = ["app_quality", "app_growth", "app_value", "app_momentum", "app_risk", "app_total", "app_total_pct", "app_ml_pct"]
PICK_ONLY = ["team", "is_repeat", "buy_number", "source", "mf_return"]


def load_series() -> dict[str, pd.DataFrame]:
    universe = pd.read_parquet(DATA_DIR / "universe" / "universe.parquet")
    equities = set(universe.loc[universe["quote_type"] == "EQUITY", "symbol"]) & set(list_symbols("prices"))
    series = {s: read_symbol("prices", s).set_index("date").sort_index()[["close", "adj_close"]] for s in equities}
    series.update(load_fool_series())
    return series


def price_features(px: pd.DataFrame, spy: pd.DataFrame, t: pd.Timestamp) -> dict:
    a = px["adj_close"].to_numpy()
    i = px.index.searchsorted(t, side="right") - 1
    if i < MIN_HISTORY or t - px.index[i] > pd.Timedelta(days=5):
        return {}
    window = a[i - 251:i + 1]
    daily = a[i - 59:i + 1] / a[i - 60:i] - 1
    j = spy.index.searchsorted(t, side="right") - 1
    s = spy["adj_close"].to_numpy()
    out = {"ret_1m": a[i] / a[i - 21] - 1, "ret_3m": a[i] / a[i - 63] - 1, "ret_6m": a[i] / a[i - 126] - 1,
           "ret_12m_ex_1m": a[i - 21] / a[i - 252] - 1, "ret_36m": a[i] / a[i - 756] - 1 if i >= 756 else np.nan,
           "sma200_gap": a[i] / a[i - 199:i + 1].mean() - 1, "vol_60d": daily.std() * np.sqrt(252),
           "drawdown_252d": a[i] / window.max() - 1, "from_52w_low": a[i] / window.min() - 1}
    out["rel_ret_3m"] = out["ret_3m"] - (s[j] / s[j - 63] - 1)
    out["rel_ret_12m_ex_1m"] = out["ret_12m_ex_1m"] - (s[j - 21] / s[j - 252] - 1)
    return out


def sample_controls(picks: pd.DataFrame, series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for date, grp in picks.groupby("rec_date"):
        taken = set(grp["symbol"]) | set(grp["yf_symbol"])
        alive = [s for s, px in series.items() if s != "SPY" and s not in taken and px.index[0] <= date - pd.Timedelta(days=400) and px.index[-1] >= date]
        n = min(len(alive), CONTROLS_PER_PICK * len(grp))
        rows += [{"rec_date": date, "symbol": s, "yf_symbol": s} for s in rng.choice(sorted(alive), n, replace=False)]
    return pd.DataFrame(rows)


def attach_app_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Our own Stock Advisor ranking as of the last month-end before rec_date: category scores, total, and cross-sectional percentiles of total / ml_score."""
    scores = pd.concat([read_symbol("scores", s) for s in list_symbols("scores")], ignore_index=True)
    ml = pd.concat([read_symbol("ml_scores", s) for s in list_symbols("ml_scores")], ignore_index=True)
    scores = scores.merge(ml, on=["symbol", "as_of"], how="left")
    scores["total_pct"] = scores.groupby("as_of")["total"].rank(pct=True)
    scores["ml_pct"] = scores.groupby("as_of")["ml_score"].rank(pct=True)
    scores = scores.drop(columns="ml_score").rename(columns={c: f"app_{c}" for c in ["quality", "growth", "value", "momentum", "risk", "total", "total_pct", "ml_pct"]})
    scores["as_of"] = scores["as_of"].astype(df["rec_date"].dtype)
    merged = pd.merge_asof(df.sort_values("rec_date"), scores.sort_values("as_of"), left_on="rec_date", right_on="as_of", by="symbol",
                           allow_exact_matches=False, tolerance=pd.Timedelta(days=62))
    return merged.drop(columns="as_of")


def attach_sic(df: pd.DataFrame) -> pd.DataFrame:
    """Industry from SEC SIC codes (assigned per company, so not today's-sector hindsight like yfinance's)."""
    picks = pd.read_parquet(CIKS_PATH).set_index("symbol")["sic"]
    lake = lake_meta(sorted(set(df.loc[df["is_pick"] == 0, "yf_symbol"]))).set_index("symbol")["sic"]
    sic = df["yf_symbol"].map(picks).fillna(df["yf_symbol"].map(lake))
    return df.assign(sic2=(sic // 100).astype("Int64"), sic3=(sic // 10).astype("Int64"))


def build() -> pd.DataFrame:
    recs = pd.read_parquet(FOOL_DIR / "recs.parquet")
    picks = recs[recs["action"] == "BUY"][["rec_date", "symbol", "yf_symbol", *PICK_ONLY]].assign(is_pick=1)
    series = load_series()
    controls = sample_controls(picks, series).assign(is_pick=0)
    df = pd.concat([picks, controls], ignore_index=True)
    df["year"] = df["rec_date"].dt.year

    spy = series["SPY"]
    feats = pd.DataFrame([price_features(series[y], spy, t) if y in series else {} for y, t in zip(df["yf_symbol"], df["rec_date"])], index=df.index)
    df = pd.concat([df, feats.reindex(columns=PRICE_FEATURES)], axis=1)
    df = pd.concat([df, fundamentals_asof(df.assign(symbol=df["yf_symbol"]), series)], axis=1)
    df = attach_sic(attach_app_scores(df))
    df = add_forward_returns(df, series)
    df["beat_spy_365d"] = df["excess_365d"].gt(0).where(df["excess_365d"].notna())
    keep = ["rec_date", "year", "symbol", "is_pick", *PICK_ONLY, "sic2", "sic3", *PRICE_FEATURES, *FUNDAMENTALS, *APP_SCORES,
            "entry_date", *[f"{p}_{h}" for h in ("30d", "90d", "180d", "365d") for p in ("ret", "excess")], "beat_spy_365d"]
    return df[keep].sort_values(["rec_date", "is_pick", "symbol"], ascending=[True, False, True], ignore_index=True)


def main() -> None:
    df = build()
    df.to_parquet(FOOL_DIR / "train.parquet", index=False)
    g = df.groupby("is_pick")
    print(f"train: {len(df)} rows; picks={int(df.is_pick.sum())}, controls={int((df.is_pick == 0).sum())}")
    print("price features present:", g["ret_12m_ex_1m"].apply(lambda s: s.notna().mean()).round(3).to_dict(),
          "| fundamentals present:", g["pe"].apply(lambda s: s.notna().mean()).round(3).to_dict(),
          "| 365d label:", g["excess_365d"].apply(lambda s: s.notna().mean()).round(3).to_dict())


if __name__ == "__main__":
    main()
