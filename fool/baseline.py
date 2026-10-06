"""Walk-forward LightGBM baselines on advisor/fool/train.parquet: expanding window, one fold per recommendation year.

selection: is_pick vs date-matched controls (does a stock 'look like' a Fool pick?)
outcome:   beat_spy_365d among picks (labels embargoed 365d so no training row's label is unknown at the test date)"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from fool.features import PRICE_FEATURES
from fool.pit import FUNDAMENTALS
from fool.ingest import FOOL_DIR

PARAMS = dict(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7)


def walk_forward(df: pd.DataFrame, features: list[str], target: str, first_year: int, embargo_days: int) -> pd.DataFrame:
    X = df[features].copy()
    X["sic2"] = df["sic2"].astype("category")
    preds = []
    for year in range(first_year, int(df["year"].max()) + 1):
        train = df["rec_date"] < pd.Timestamp(year, 1, 1) - pd.Timedelta(days=embargo_days)
        test = df["year"] == year
        if test.sum() < 10 or train.sum() < 100 or df.loc[test, target].nunique() < 2 or df.loc[train, target].nunique() < 2:
            continue
        model = lgb.LGBMClassifier(**PARAMS).fit(X[train], df.loc[train, target].astype(int))
        preds.append(pd.DataFrame({"year": year, "y": df.loc[test, target].astype(int), "p": model.predict_proba(X[test])[:, 1]}))
    return pd.concat(preds)


def summarize(name: str, res: pd.DataFrame) -> None:
    by_year = res.groupby("year").apply(lambda g: roc_auc_score(g["y"], g["p"]) if g["y"].nunique() > 1 else np.nan, include_groups=False)
    print(f"{name}: pooled OOS AUC {roc_auc_score(res['y'], res['p']):.3f} (n={len(res)}, base rate {res['y'].mean():.2f}); "
          f"mean yearly AUC {by_year.mean():.3f}, years > 0.5: {(by_year > 0.5).sum()}/{by_year.notna().sum()}")


def main() -> None:
    df = pd.read_parquet(FOOL_DIR / "train.parquet")
    sel = df.dropna(subset=PRICE_FEATURES[:4])
    summarize("selection, price features", walk_forward(sel, PRICE_FEATURES, "is_pick", 2008, 0))
    summarize("selection, price + fundamentals", walk_forward(sel, PRICE_FEATURES + FUNDAMENTALS, "is_pick", 2008, 0))
    picks = df[(df["is_pick"] == 1)].dropna(subset=PRICE_FEATURES[:4] + ["beat_spy_365d"])
    summarize("outcome among picks, price features", walk_forward(picks, PRICE_FEATURES, "beat_spy_365d", 2008, 365))


if __name__ == "__main__":
    main()
