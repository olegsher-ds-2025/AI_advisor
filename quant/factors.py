"""Point-in-time factors per symbol at each month-end, from advisor/financials + advisor/prices.

A fundamental is only used once its filing date is before the as-of date.
Annual (FY) figures are used for income-statement ratios; TTM needs Q4 derived
from FY minus 9M, which the financials dataset does not carry yet.

Usage:
    python -m quant.factors AAPL MSFT NVDA     # no args = every symbol with financials
"""
import argparse

import numpy as np
import pandas as pd

from collector.store import list_symbols, read_symbol, upsert_symbol

TRADING_DAYS = 252
BALANCE_COLUMNS = ["assets", "liabilities", "cash", "debt", "equity", "shares"]


def price_factors(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.sort_values("date").set_index("date")
    adj, daily_ret = prices["adj_close"], prices["adj_close"].pct_change()
    return pd.DataFrame(
        {
            "close": prices["close"],
            "ret_1m": adj.pct_change(21),
            "ret_3m": adj.pct_change(63),
            "ret_6m": adj.pct_change(126),
            "ret_12m_ex_1m": adj.shift(21) / adj.shift(TRADING_DAYS) - 1,
            "sma200_gap": adj / adj.rolling(200).mean() - 1,
            "vol_60d": daily_ret.rolling(60).std() * np.sqrt(TRADING_DAYS),
            "drawdown_252d": adj / adj.rolling(TRADING_DAYS).max() - 1,
        }
    )


def _ratio(num, den):
    return num / den if pd.notna(num) and pd.notna(den) and den != 0 else np.nan


def _growth(current, prior):
    return _ratio(current - prior, abs(prior)) if pd.notna(current) and pd.notna(prior) else np.nan


def fundamental_factors(fin: pd.DataFrame, as_of: pd.Timestamp, close: float) -> dict:
    known = fin[fin["filed"] < as_of].sort_values("filed")
    if known.empty:
        return {}

    # latest filed value per (period, column); groupby.last skips NaN so later partial filings don't blank earlier values
    annual = known[known["period_type"] == "FY"].groupby("period").last().sort_index()
    latest_balance = known.sort_values(["period", "filed"]).groupby("period").last().sort_index()[BALANCE_COLUMNS].ffill().iloc[-1]

    factors = {}
    if not annual.empty:
        current = annual.iloc[-1]
        prior = annual[(current.name - annual.index).days.to_series(index=annual.index).between(350, 380)]
        prior = prior.iloc[-1] if not prior.empty else pd.Series(dtype=float)
        factors.update(
            net_margin=_ratio(current["net_income"], current["revenue"]),
            roe=_ratio(current["net_income"], current["equity"]) if current["equity"] > 0 else np.nan,
            roa=_ratio(current["net_income"], current["assets"]),
            revenue_growth=_growth(current["revenue"], prior.get("revenue", np.nan)),
            net_income_growth=_growth(current["net_income"], prior.get("net_income", np.nan)),
            eps_growth=_growth(current["eps"], prior.get("eps", np.nan)),
            pe=_ratio(close, current["eps"]) if current["eps"] > 0 else np.nan,
        )
        market_cap = close * latest_balance["shares"]
        factors["ps"] = _ratio(market_cap, current["revenue"])
        factors["pb"] = _ratio(market_cap, latest_balance["equity"]) if latest_balance["equity"] > 0 else np.nan
    factors["debt_to_equity"] = _ratio(latest_balance["debt"], latest_balance["equity"]) if latest_balance["equity"] > 0 else np.nan
    factors["liabilities_to_assets"] = _ratio(latest_balance["liabilities"], latest_balance["assets"])
    return factors


def compute_metrics(symbol: str, fin: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    price_table = price_factors(prices)
    month_ends = price_table.groupby(price_table.index.to_period("M")).tail(1)
    rows = []
    for as_of, price_row in month_ends.iterrows():
        rows.append({"symbol": symbol, "as_of": as_of, **price_row.drop("close"), **fundamental_factors(fin, as_of, price_row["close"])})
    return pd.DataFrame(rows)


def run(symbols: list[str]):
    for symbol in symbols or list_symbols("financials"):
        symbol = symbol.upper()
        fin, prices = read_symbol("financials", symbol), read_symbol("prices", symbol)
        if fin is None or prices is None:
            print(f"[factors] {symbol}: missing financials or prices, skipping")
            continue
        metrics = compute_metrics(symbol, fin, prices)
        path = upsert_symbol("metrics", symbol, metrics, ["as_of"])
        print(f"[factors] {symbol}: {len(metrics)} month-ends -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    run(parser.parse_args().symbols)
