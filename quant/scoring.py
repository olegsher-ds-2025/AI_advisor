"""Stage-1 scoring: cross-sectional percentile ranks of each factor per as-of date,
averaged into category scores (0-100) and a total. These are research scores to
sort a universe by, not buy/sell signals.

Usage:
    python -m quant.scoring
"""
import pandas as pd

from collector.store import list_symbols, read_symbol, upsert_symbol

# factor -> True when a higher value is better
CATEGORIES = {
    "quality": {"net_margin": True, "roe": True, "roa": True, "debt_to_equity": False, "liabilities_to_assets": False},
    "growth": {"revenue_growth": True, "net_income_growth": True, "eps_growth": True},
    "value": {"pe": False, "ps": False, "pb": False},
    "momentum": {"ret_3m": True, "ret_6m": True, "ret_12m_ex_1m": True, "sma200_gap": True},
    "risk": {"vol_60d": False, "drawdown_252d": True},
}


def score(metrics: pd.DataFrame) -> pd.DataFrame:
    """Rank within each as_of date so a score never depends on another date's universe."""
    out = metrics[["symbol", "as_of"]].copy()
    for category, factors in CATEGORIES.items():
        ranks = pd.DataFrame(
            {f: metrics.groupby("as_of")[f].rank(pct=True, ascending=higher) for f, higher in factors.items()}
        )
        out[category] = ranks.mean(axis=1) * 100
    out["total"] = out[list(CATEGORIES)].mean(axis=1)
    return out


def run():
    symbols = list_symbols("metrics")
    metrics = pd.concat([read_symbol("metrics", s) for s in symbols], ignore_index=True)
    scores = score(metrics)
    for symbol, rows in scores.groupby("symbol"):
        upsert_symbol("scores", symbol, rows, ["as_of"])
    print(f"[scoring] {len(symbols)} symbols, {len(scores)} rows")


if __name__ == "__main__":
    run()
