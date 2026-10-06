"""Where does our own Stock Advisor ranking put Fool's picks? (point-in-time, from advisor/scores + advisor/ml_scores)"""
import pandas as pd

from fool.features import APP_SCORES
from fool.ingest import FOOL_DIR


def main() -> None:
    df = pd.read_parquet(FOOL_DIR / "train.parquet")
    df = df.dropna(subset=["app_total_pct"])
    print(f"rows with an app ranking: picks={int(df.is_pick.sum())}, controls={int((1 - df.is_pick).sum())}\n")
    print("percentile of total / ml_score within the universe at the pick date (50 = no edge):")
    print((df.groupby("is_pick")[["app_total_pct", "app_ml_pct"]].median() * 100).round(1).to_string(), "\n")
    p = df[df.is_pick == 1]
    print("share of picks in our top quartile / top decile by total:", f"{(p.app_total_pct >= .75).mean():.0%} / {(p.app_total_pct >= .9).mean():.0%}")
    print("category scores (median, 0-100):\n", df.groupby("is_pick")[["app_quality", "app_growth", "app_value", "app_momentum", "app_risk"]].median().round(1).to_string(), "\n")
    lab = p.dropna(subset=["excess_365d"])
    print(f"does our ranking separate good picks from bad? Spearman vs excess_365d (n={len(lab)}):")
    print(lab[APP_SCORES + ["excess_365d"]].corr(method="spearman")["excess_365d"].drop("excess_365d").round(3).to_string())
    top = lab[lab.app_total_pct >= .5]["excess_365d"]; bottom = lab[lab.app_total_pct < .5]["excess_365d"]
    print(f"\nmedian excess_365d: our top half {top.median():+.1%} (n={len(top)}) vs bottom half {bottom.median():+.1%} (n={len(bottom)})")


if __name__ == "__main__":
    main()
