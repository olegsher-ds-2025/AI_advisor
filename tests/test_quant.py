import numpy as np
import pandas as pd

from collector.financials import COLUMNS
from quant.factors import fundamental_factors
from quant.scoring import score


def fin_row(period, period_type, filed, **values):
    return {**dict.fromkeys(COLUMNS, np.nan), "period": pd.Timestamp(period), "period_type": period_type, "filed": pd.Timestamp(filed), **values}


def test_fundamentals_ignore_filings_after_the_as_of_date():
    fin = pd.DataFrame([
        fin_row("2022-12-31", "FY", "2023-02-01", revenue=100.0, net_income=10.0, equity=50.0, eps=1.0, shares=10.0),
        fin_row("2023-12-31", "FY", "2024-02-01", revenue=200.0, net_income=40.0, equity=80.0, eps=4.0, shares=10.0),
    ])

    before = fundamental_factors(fin, pd.Timestamp("2024-01-31"), close=20.0)
    after = fundamental_factors(fin, pd.Timestamp("2024-02-29"), close=20.0)

    assert before["net_margin"] == 0.1
    assert np.isnan(before["revenue_growth"])
    assert after["net_margin"] == 0.2
    assert after["revenue_growth"] == 1.0
    assert after["pe"] == 5.0


def test_filing_on_the_as_of_date_is_not_yet_known():
    fin = pd.DataFrame([fin_row("2023-12-31", "FY", "2024-02-01", revenue=100.0, net_income=10.0, equity=50.0, eps=1.0)])

    assert fundamental_factors(fin, pd.Timestamp("2024-02-01"), close=10.0) == {}


def test_non_positive_equity_has_no_roe_or_leverage():
    fin = pd.DataFrame([fin_row("2023-12-31", "FY", "2024-02-01", revenue=100.0, net_income=10.0, equity=-5.0, debt=20.0)])

    factors = fundamental_factors(fin, pd.Timestamp("2024-03-31"), close=10.0)

    assert np.isnan(factors["roe"]) and np.isnan(factors["debt_to_equity"])


def test_scores_rank_within_each_date_and_invert_lower_is_better():
    as_of = pd.Timestamp("2024-01-31")
    metrics = pd.DataFrame({"symbol": ["A", "B", "C"], "as_of": as_of, "roe": [0.1, 0.2, 0.3], "pe": [10.0, 20.0, 30.0]})
    for col in ["net_margin", "roa", "debt_to_equity", "liabilities_to_assets", "revenue_growth", "net_income_growth",
                "eps_growth", "ps", "pb", "ret_3m", "ret_6m", "ret_12m_ex_1m", "sma200_gap", "vol_60d", "drawdown_252d"]:
        metrics[col] = np.nan

    scored = score(metrics).set_index("symbol")

    assert scored.loc["C", "quality"] > scored.loc["A", "quality"]
    assert scored.loc["A", "value"] > scored.loc["C", "value"]
