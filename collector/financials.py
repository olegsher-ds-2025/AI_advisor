"""Builds point-in-time financials from the SEC facts already collected in
<STOCK_MARKET_DIR>/fundamentals/symbol=*/facts.parquet.

Usage:
    python -m collector.financials AAPL MSFT NVDA
"""
import argparse

import pandas as pd

from collector.store import read_facts, read_symbol, upsert_symbol

# Order is precedence: the first concept present in a filing wins for its column.
CONCEPT_MAP = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "GrossProfit": "gross_profit",
    "OperatingIncomeLoss": "operating_income",
    "NetIncomeLoss": "net_income",
    "EarningsPerShareDiluted": "eps",
    "Assets": "assets",
    "Liabilities": "liabilities",
    "CashAndCashEquivalentsAtCarryingValue": "cash",
    "StockholdersEquity": "equity",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cf",
    "PaymentsForCapitalExpenditures": "capex",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "PaymentsToAcquireProductiveAssets": "capex",
    "CommonStockSharesOutstanding": "shares",
    "LongTermDebt": "debt",
    "LongTermDebtNoncurrent": "debt",
}
CONCEPT_RANK = {concept: rank for rank, concept in enumerate(CONCEPT_MAP)}

COLUMNS = list(dict.fromkeys(CONCEPT_MAP.values())) + ["free_cash_flow"]
FORM_TO_PERIOD_TYPE = {"10-K": "FY", "10-K/A": "FY", "10-Q": "Q", "10-Q/A": "Q"}
ALLOWED_UNITS = {"USD", "USD/shares", "shares"}
# flow facts carry a start date; a 10-Q also reports 6M/9M YTD values for the same period_end
DURATION_DAYS = {"Q": (80, 100), "FY": (350, 380)}
KEYS = ["period", "period_type", "accn"]
# cumulative (6M/9M YTD, FY) duration -> days the previous cumulative period of the same fiscal year ends earlier
CUMULATIVE_DURATION_DAYS = (170, 380)
PREVIOUS_STEP_DAYS = (80, 100)


def derive_quarters(facts: pd.DataFrame) -> pd.DataFrame:
    """Discrete-quarter facts from cumulative ones: Q2 = 6M - 3M, Q3 = 9M - 6M, Q4 = FY - 9M.

    Cash-flow facts are only reported cumulatively in a 10-Q, so TTM needs this. The derived fact
    takes the filing of the cumulative value, the later of its two inputs, so `filed` stays point-in-time.
    """
    flows = facts[facts["period_start"].notna()].assign(
        start=lambda d: pd.to_datetime(d["period_start"]), end=lambda d: pd.to_datetime(d["period_end"])
    )
    flows = flows.assign(days=(flows["end"] - flows["start"]).dt.days)
    cumulative = flows[flows["days"].between(*CUMULATIVE_DURATION_DAYS)]
    earlier = flows[["concept", "unit", "start", "end", "value", "filed_at"]].rename(
        columns={"end": "prior_end", "value": "prior_value", "filed_at": "prior_filed"}
    )
    pairs = cumulative.merge(earlier, on=["concept", "unit", "start"])
    step = (pairs["end"] - pairs["prior_end"]).dt.days
    pairs = pairs[step.between(*PREVIOUS_STEP_DAYS)]
    pairs = pairs.sort_values("prior_filed").drop_duplicates(["concept", "unit", "start", "end", "accession_no", "prior_end"])
    derived = pairs.assign(
        value=pairs["value"] - pairs["prior_value"],
        period_start=(pairs["prior_end"] + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d"),
        form=pairs["form"].map(lambda f: "10-Q/A" if f.endswith("/A") else "10-Q"),
    )
    return derived[facts.columns]


def build_financials(symbol: str, facts: pd.DataFrame) -> pd.DataFrame:
    """One row per (period, period_type, accn) so restatements are kept and `filed` is a valid point-in-time cutoff."""
    facts = pd.concat([facts, derive_quarters(facts)], ignore_index=True)
    df = facts.assign(
        period_type=facts["form"].map(FORM_TO_PERIOD_TYPE),
        column=facts["concept"].map(CONCEPT_MAP),
        rank=facts["concept"].map(CONCEPT_RANK),
    )
    df = df[df["period_type"].notna() & df["column"].notna() & df["unit"].isin(ALLOWED_UNITS)]

    start = pd.to_datetime(df["period_start"])
    days = (pd.to_datetime(df["period_end"]) - start).dt.days
    low = df["period_type"].map(lambda t: DURATION_DAYS[t][0])
    high = df["period_type"].map(lambda t: DURATION_DAYS[t][1])
    df = df[start.isna() | ((days >= low) & (days <= high))]

    index = ["period_end", "period_type", "accession_no", "form", "filed_at"]
    wide = (
        df.sort_values("rank", kind="stable")
        .drop_duplicates(index + ["column"], keep="first")
        .pivot(index=index, columns="column", values="value")
        .reindex(columns=COLUMNS)
        .reset_index()
        .rename(columns={"period_end": "period", "accession_no": "accn", "filed_at": "filed"})
    )
    wide.columns.name = None
    wide["free_cash_flow"] = wide["operating_cf"] - wide["capex"].abs()
    wide["period"] = pd.to_datetime(wide["period"])
    wide["filed"] = pd.to_datetime(wide["filed"])
    wide.insert(0, "symbol", symbol)
    return wide


def run(symbols: list[str]):
    for symbol in symbols:
        symbol = symbol.upper()
        facts = read_facts(symbol)
        extra = read_symbol("facts_extra", symbol)
        if facts is not None and extra is not None:
            facts = pd.concat([facts, extra], ignore_index=True)
        if facts is None:
            print(f"[financials] {symbol}: no facts.parquet under fundamentals/, skipping")
            continue
        rows = build_financials(symbol, facts)
        path = upsert_symbol("financials", symbol, rows, KEYS)
        print(f"[financials] {symbol}: {len(rows)} rows -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+")
    run(parser.parse_args().symbols)
