"""Monthly-rebalance backtest of the top-N symbols by a score column, equal weight,
against SPY, QQQ and the equal-weighted eligible universe. Scores at a month-end
use only data known by then, so the holding return runs to the next month-end.

Usage:
    python -m quant.backtest [--top 30] [--score total ml_score] [--cost-bps 10]

Strategy returns are net of costs: `cost_bps` per unit of traded weight, charged at each rebalance.
The sector-matched benchmark holds each pick's SPDR sector ETF instead of the pick; it needs
`python -m collector.market XLK XLF ...` prices and `python -m collector.universe` sectors.
"""
import argparse

import numpy as np
import pandas as pd

from collector.store import DATA_DIR, list_symbols, read_symbol
from collector.universe import read_universe

BENCHMARKS = ["SPY", "QQQ"]
SECTOR_ETFS = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Communication Services": "XLC", "Energy": "XLE", "Industrials": "XLI",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}
MIN_CATEGORY_SCORES = 4  # skip the first months, before 12-month momentum exists


def load_scores() -> pd.DataFrame:
    scores = pd.concat([read_symbol("scores", s) for s in list_symbols("scores")], ignore_index=True)
    categories = scores.columns.difference(["symbol", "as_of", "total"])
    scores = scores[scores[categories].notna().sum(axis=1) >= MIN_CATEGORY_SCORES]
    ml_symbols = list_symbols("ml_scores")
    if ml_symbols:
        ml = pd.concat([read_symbol("ml_scores", s) for s in ml_symbols], ignore_index=True)
        scores = scores.merge(ml, on=["symbol", "as_of"], how="left")
    return scores


def month_end_prices(symbols: list[str], as_of_dates: pd.DatetimeIndex) -> pd.DataFrame:
    close = {}
    for symbol in symbols:
        prices = read_symbol("prices", symbol)
        if prices is not None:
            close[symbol] = prices.set_index("date")["adj_close"].reindex(as_of_dates)
    return pd.DataFrame(close)


def forward_returns(symbols: list[str], as_of_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Return from each as-of date to the next one, per symbol."""
    wide = month_end_prices(symbols, as_of_dates)
    return wide.shift(-1) / wide - 1


def eligible_symbols(symbols: list[str]) -> list[str]:
    try:
        universe = read_universe()
    except FileNotFoundError:
        return symbols
    equities = set(universe.loc[universe["quote_type"] == "EQUITY", "symbol"])
    return [s for s in symbols if s in equities]


def sector_benchmarks(symbols: list[str]) -> pd.Series:
    """Sector ETF per symbol, SPY where the sector is unknown."""
    try:
        sectors = read_universe().set_index("symbol")["sector"]
    except FileNotFoundError:
        sectors = pd.Series(dtype=object)
    return pd.Series({s: SECTOR_ETFS.get(sectors.get(s), "SPY") for s in symbols})


def run_strategy(
    scores: pd.DataFrame, forward: pd.DataFrame, score_column: str, top_n: int,
    cost_bps: float = 0, benchmark_for: pd.Series | None = None,
) -> pd.DataFrame:
    rows, previous = [], pd.Series(dtype=float)
    for as_of, date_scores in scores.groupby("as_of"):
        if as_of not in forward.index or forward.loc[as_of].isna().all():
            continue
        picks = date_scores.dropna(subset=[score_column]).nlargest(top_n, score_column)["symbol"]
        if picks.empty:
            continue
        weights = pd.Series(1 / len(picks), index=picks)
        traded = weights.sub(previous, fill_value=0).abs().sum()
        row = {"as_of": as_of, "strategy": forward.loc[as_of, picks].mean() - traded * cost_bps / 1e4, "turnover": traded / 2}
        if benchmark_for is not None:
            row["sector_benchmark"] = forward.loc[as_of, benchmark_for[picks].values].mean()
        rows.append(row)
        previous = weights
    return pd.DataFrame(rows).set_index("as_of")


def performance(returns: pd.Series, benchmark: pd.Series | None = None) -> dict:
    returns = returns.dropna()
    equity = (1 + returns).cumprod()
    downside = returns[returns < 0].std() * np.sqrt(12)
    stats = {
        "cagr": equity.iloc[-1] ** (12 / len(returns)) - 1,
        "volatility": returns.std() * np.sqrt(12),
        "max_drawdown": (equity / equity.cummax() - 1).min(),
        "sharpe": returns.mean() * 12 / (returns.std() * np.sqrt(12)),
        "sortino": returns.mean() * 12 / downside if downside else np.nan,
    }
    if benchmark is not None:
        stats["win_rate_vs_spy"] = (returns > benchmark.reindex(returns.index)).mean()
    return stats


def run(top_n: int, score_columns: list[str], cost_bps: float):
    symbols = eligible_symbols(list_symbols("scores"))
    scores = load_scores()
    scores = scores[scores["symbol"].isin(symbols)]
    benchmark_for = sector_benchmarks(symbols)
    etfs = sorted(set(benchmark_for) - {"SPY"})
    forward = forward_returns(symbols + BENCHMARKS + etfs, pd.DatetimeIndex(sorted(scores["as_of"].unique())))
    if not set(etfs) <= set(forward.columns):
        print(f"[backtest] no prices for sector ETFs {sorted(set(etfs) - set(forward.columns))}, sector-matched benchmark skipped")
        benchmark_for = None

    results = {c: run_strategy(scores, forward, c, top_n, cost_bps, benchmark_for) for c in score_columns}
    index = pd.DatetimeIndex(sorted(set().union(*(r.index for r in results.values()))))
    returns = pd.DataFrame(
        {
            **{f"top{top_n}_{c}": r["strategy"] for c, r in results.items()},
            **({f"top{top_n}_{c}_sector_matched": r["sector_benchmark"] for c, r in results.items()} if benchmark_for is not None else {}),
            "equal_weight_universe": forward[symbols].mean(axis=1),
            **{b: forward[b] for b in BENCHMARKS},
        }
    ).loc[index].dropna()

    summary = pd.DataFrame({name: performance(col, returns["SPY"]) for name, col in returns.items()}).T
    print(f"{returns.index.min().date()} -> {returns.index.max().date()}, {len(returns)} monthly periods, "
          "avg turnover " + ", ".join(f"{c} {r['turnover'].mean():.0%}" for c, r in results.items()))
    print(summary.round(3).to_string())

    out = DATA_DIR / "backtest" / f"returns_top{top_n}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    returns.to_parquet(out)
    print(f"[backtest] monthly returns -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--cost-bps", type=float, default=10, help="cost per unit of traded weight, in basis points")
    parser.add_argument("--score", nargs="+", default=["total"], help="score columns, e.g. total ml_score")
    args = parser.parse_args()
    run(args.top, args.score, args.cost_bps)
