"""Builds point-in-time financials from the SEC facts already collected in
<STOCK_MARKET_DIR>/fundamentals/symbol=*/facts.parquet.

Usage:
    python -m collector.financials AAPL MSFT NVDA
"""
import argparse

import pandas as pd

from collector.store import read_facts, upsert_symbol

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


def build_financials(symbol: str, facts: pd.DataFrame) -> pd.DataFrame:
    """One row per (period, period_type, accn) so restatements are kept and `filed` is a valid point-in-time cutoff."""
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
        df.sort_values("rank")
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
