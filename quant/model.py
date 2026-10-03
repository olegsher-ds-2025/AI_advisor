"""Stage-2 scoring: LightGBM predicting 12-month forward excess return (vs the
universe median) from cross-sectionally ranked factors, trained walk-forward.

A model predicting month T only trains on months whose 12-month outcome was
already realized by T, so no label ever looks past the prediction date.

Usage:
    python -m quant.model
"""
import lightgbm as lgb
import pandas as pd

from collector.store import list_symbols, read_symbol, upsert_symbol
from quant.backtest import eligible_symbols, month_end_prices

HORIZON = 12  # months
MIN_TRAIN_DATES = 12
PARAMS = dict(n_estimators=200, learning_rate=0.05, num_leaves=15, min_child_samples=100,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def load_dataset() -> pd.DataFrame:
    symbols = eligible_symbols(list_symbols("metrics"))
    metrics = pd.concat([read_symbol("metrics", s) for s in symbols], ignore_index=True)
    prices = month_end_prices(symbols, pd.DatetimeIndex(sorted(metrics["as_of"].unique())))
    forward = prices.shift(-HORIZON) / prices - 1
    excess = forward.sub(forward.median(axis=1), axis=0)
    labels = excess.stack().rename("target").rename_axis(["as_of", "symbol"]).reset_index()

    features = [c for c in metrics.columns if c not in ("symbol", "as_of")]
    metrics[features] = metrics.groupby("as_of")[features].rank(pct=True)
    return metrics.merge(labels, on=["as_of", "symbol"], how="left")


def walk_forward(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    features = [c for c in data.columns if c not in ("symbol", "as_of", "target")]
    dates = sorted(data["as_of"].unique())
    predictions, importance = [], pd.Series(0.0, index=features)

    for i in range(HORIZON + MIN_TRAIN_DATES, len(dates)):
        train = data[data["as_of"].isin(dates[: i - HORIZON + 1]) & data["target"].notna()]
        test = data[data["as_of"] == dates[i]]
        model = lgb.LGBMRegressor(**PARAMS).fit(train[features], train["target"])
        predictions.append(test[["symbol", "as_of"]].assign(ml_score=model.predict(test[features])))
        importance += pd.Series(model.feature_importances_, index=features)
    return pd.concat(predictions, ignore_index=True), importance / importance.sum()


def rank_ic(predictions: pd.DataFrame, data: pd.DataFrame) -> pd.Series:
    joined = predictions.merge(data[["symbol", "as_of", "target"]], on=["symbol", "as_of"]).dropna()
    return joined.groupby("as_of").apply(lambda g: g["ml_score"].corr(g["target"], method="spearman"), include_groups=False)


def run():
    data = load_dataset()
    predictions, importance = walk_forward(data)
    for symbol, rows in predictions.groupby("symbol"):
        upsert_symbol("ml_scores", symbol, rows, ["as_of"])

    ic = rank_ic(predictions, data)
    print(f"[model] {predictions['as_of'].nunique()} predicted months, {len(predictions)} rows")
    print(f"[model] out-of-sample rank IC vs realized {HORIZON}m excess return: "
          f"mean {ic.mean():.3f} over {len(ic)} months, positive in {(ic > 0).mean():.0%}")
    print(importance.sort_values(ascending=False).round(3).head(8).to_string())


if __name__ == "__main__":
    run()
