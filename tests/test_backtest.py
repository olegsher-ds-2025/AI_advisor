import numpy as np
import pandas as pd

from quant.backtest import performance, run_strategy


def test_run_strategy_picks_top_scores_and_measures_turnover():
    dates = pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29"])
    scores = pd.DataFrame({
        "as_of": [dates[0]] * 3 + [dates[1]] * 3,
        "symbol": ["A", "B", "C"] * 2,
        "total": [90, 80, 10, 10, 80, 90],
    })
    forward = pd.DataFrame({"A": [0.10, 0.0, np.nan], "B": [0.0, 0.0, np.nan], "C": [0.0, 0.20, np.nan]}, index=dates)

    result = run_strategy(scores, forward, "total", top_n=2)

    assert result["strategy"].tolist() == [0.05, 0.10]
    assert result["turnover"].tolist() == [0.5, 0.5]


def test_performance_cagr_and_drawdown():
    returns = pd.Series([0.10, -0.10, 0.10, 0.10], index=pd.date_range("2024-01-31", periods=4, freq="ME"))

    stats = performance(returns)

    assert round(stats["max_drawdown"], 3) == -0.1
    assert round(stats["cagr"], 3) == round((1.1 * 0.9 * 1.1 * 1.1) ** 3 - 1, 3)


def test_transaction_costs_are_charged_on_traded_weight():
    dates = pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29"])
    scores = pd.DataFrame({
        "as_of": [dates[0]] * 3 + [dates[1]] * 3,
        "symbol": ["A", "B", "C"] * 2,
        "total": [90, 80, 10, 10, 80, 90],
    })
    forward = pd.DataFrame({"A": [0.10, 0.0, np.nan], "B": [0.0, 0.0, np.nan], "C": [0.0, 0.20, np.nan]}, index=dates)

    result = run_strategy(scores, forward, "total", top_n=2, cost_bps=100)

    # month 1 buys 100% of the book, month 2 swaps half of it (sells A, buys C)
    assert np.allclose(result["strategy"], [0.05 - 0.01, 0.10 - 0.01])


def test_sector_benchmark_holds_each_picks_sector_etf():
    dates = pd.to_datetime(["2024-01-31", "2024-02-29"])
    scores = pd.DataFrame({"as_of": dates[0], "symbol": ["A", "B"], "total": [90, 80]})
    forward = pd.DataFrame({"A": [0.10, np.nan], "B": [0.0, np.nan], "XLK": [0.04, np.nan], "XLE": [0.02, np.nan]}, index=dates)

    result = run_strategy(scores, forward, "total", top_n=2, benchmark_for=pd.Series({"A": "XLK", "B": "XLE"}))

    assert np.allclose(result["sector_benchmark"], [0.03])
