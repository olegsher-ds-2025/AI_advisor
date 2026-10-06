"""Recommended-or-not classifier: y = is_pick (Fool BUY vs date-matched random control) from information available on the recommendation date.

Split by time, never at random: train < 2017, validation 2017-2020 (model choice), test 2021+ (touched once).
Feature sets are compared because fundamentals are missing far more often for picks (delisted names) than for controls, so NaN-ness alone separates the
classes; the `complete cases` row restricts to rows where both classes have fundamentals and is the honest read on them."""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fool.features import PRICE_FEATURES
from fool.ingest import FOOL_DIR
from fool.pit import FUNDAMENTALS

TRAIN_END, VAL_END = 2016, 2020
FUNDAMENTAL_FEATURES = [f for f in FUNDAMENTALS if f != "filing_age_days"]
LGB = dict(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=30, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
           reg_lambda=5.0, verbose=-1, random_state=7)


def prepare(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    X = df[features].astype(float).copy()
    if "market_cap" in X:
        X["market_cap"] = np.log10(X["market_cap"].where(X["market_cap"] > 0))
    for c in ("pe", "ps", "pb"):
        if c in X:
            X[c] = X[c].clip(-200, 200)
    return X.replace([np.inf, -np.inf], np.nan)


def models() -> dict:
    return {"logistic": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)),
            "lightgbm": lgb.LGBMClassifier(**LGB)}


def precision_at_decile(y: pd.Series, p: np.ndarray, dates: pd.Series) -> float:
    """Mean over recommendation dates of: share of true picks among the top 10% scored rows of that date's cohort."""
    frame = pd.DataFrame({"y": y.to_numpy(), "p": p, "d": dates.to_numpy()})
    hits = []
    for _, g in frame.groupby("d"):
        if g["y"].sum():
            k = max(1, int(round(len(g) * 0.1)))
            hits.append(g.nlargest(k, "p")["y"].sum() / g["y"].sum())
    return float(np.mean(hits))


def evaluate(df: pd.DataFrame, features: list[str], label: str) -> pd.DataFrame:
    X = prepare(df, features)
    y = df["is_pick"].astype(int)
    train, val, test = df["year"] <= TRAIN_END, df["year"].between(TRAIN_END + 1, VAL_END), df["year"] > VAL_END
    rows = []
    for name, model in models().items():
        model.fit(X[train], y[train])
        for split, mask in (("val", val), ("test", test)):
            p = model.predict_proba(X[mask])[:, 1]
            rows.append({"features": label, "model": name, "split": split, "n": int(mask.sum()), "base_rate": round(y[mask].mean(), 3),
                         "roc_auc": roc_auc_score(y[mask], p), "pr_auc": average_precision_score(y[mask], p),
                         "pick_recall_in_top10%": precision_at_decile(y[mask], p, df.loc[mask, "rec_date"])})
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_parquet(FOOL_DIR / "train.parquet")
    df = df.dropna(subset=PRICE_FEATURES[:4])
    sic = pd.get_dummies(df["sic2"].astype("Int64").astype(str), prefix="sic2", dtype=float)
    df = pd.concat([df, sic], axis=1)
    sic_cols = [c for c in sic.columns if sic[c].sum() >= 30]
    complete = df.dropna(subset=["pe", "ps", "revenue_growth", "market_cap"])
    results = [evaluate(df, PRICE_FEATURES, "price"),
               evaluate(df, PRICE_FEATURES + sic_cols, "price + industry"),
               evaluate(df, PRICE_FEATURES + FUNDAMENTAL_FEATURES + sic_cols, "price + fundamentals + industry (all rows)"),
               evaluate(complete, PRICE_FEATURES + FUNDAMENTAL_FEATURES + sic_cols, "price + fundamentals + industry (complete cases)")]
    out = pd.concat(results, ignore_index=True)
    pd.set_option("display.width", 250)
    print(out.round(3).to_string(index=False))
    print(f"\nclass balance (picks): train {df[df.year <= TRAIN_END].is_pick.mean():.3f}, test {df[df.year > VAL_END].is_pick.mean():.3f}; complete-case rows {len(complete)}, picks {int(complete.is_pick.sum())}")


if __name__ == "__main__":
    main()
