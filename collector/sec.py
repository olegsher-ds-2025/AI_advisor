"""SEC EDGAR collector - pulls company facts (XBRL) with no API key.

Usage:
    python -m collector.sec AAPL MSFT NVDA
"""
import os
import sys
import time
from datetime import date

import requests

from collector.db import get_connection, upsert

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# us-gaap XBRL concept -> financials column. Order is precedence: the first
# concept present in a filing wins for its column.
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
}

ALLOWED_UNITS = {"USD", "USD/shares", "shares"}
# flow facts carry a start date; a 10-Q also reports 6M/9M YTD values for the same end date
DURATION_DAYS = {"Q": (80, 100), "FY": (350, 380)}

FORM_TO_PERIOD_TYPE = {"10-K": "FY", "10-Q": "Q"}


def _headers() -> dict:
    user_agent = os.environ.get("SEC_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "Set SEC_USER_AGENT env var to 'Name contact@email' per SEC fair access policy"
        )
    return {"User-Agent": user_agent}


def load_ticker_cik_map() -> dict[str, dict]:
    data = _get(TICKERS_URL).json()

    # shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    by_ticker = {}
    for entry in data.values():
        by_ticker[entry["ticker"].upper()] = {
            "cik": entry["cik_str"],
            "name": entry["title"],
        }
    return by_ticker


def fetch_company_facts(cik: int) -> dict:
    return _get(FACTS_URL.format(cik=cik)).json()


def _duration_matches(entry: dict, period_type: str) -> bool:
    start = entry.get("start")
    if start is None:
        return True
    days = (date.fromisoformat(entry["end"]) - date.fromisoformat(start)).days
    low, high = DURATION_DAYS[period_type]
    return low <= days <= high


def parse_financials(ticker: str, facts: dict) -> list[dict]:
    """One row per (period, period_type, accn) so restatements are kept and `filed` is usable as a point-in-time cutoff."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    records: dict[tuple, dict] = {}

    for concept, column in CONCEPT_MAP.items():
        concept_data = us_gaap.get(concept)
        if not concept_data:
            continue
        for unit, unit_entries in concept_data.get("units", {}).items():
            if unit not in ALLOWED_UNITS:
                continue
            for entry in unit_entries:
                form = entry.get("form")
                period_type = FORM_TO_PERIOD_TYPE.get(form)
                if period_type is None or not _duration_matches(entry, period_type):
                    continue
                end = entry["end"]
                key = (end, period_type, entry["accn"])
                record = records.setdefault(
                    key,
                    {
                        "ticker": ticker,
                        "period": end,
                        "period_type": period_type,
                        "accn": entry["accn"],
                        "form": form,
                        "filed": entry["filed"],
                        "fy": entry.get("fy"),
                        "fp": entry.get("fp"),
                    },
                )
                record.setdefault(column, entry.get("val"))

    rows = []
    for record in records.values():
        operating_cf = record.get("operating_cf")
        capex = record.get("capex")
        if operating_cf is not None and capex is not None:
            record["free_cash_flow"] = operating_cf - abs(capex)
        for col in (
            "revenue", "gross_profit", "operating_income", "net_income", "ebitda",
            "eps", "assets", "liabilities", "cash", "debt", "equity", "operating_cf",
            "capex", "free_cash_flow", "shares",
        ):
            record.setdefault(col, None)
        rows.append(record)
    return rows


def _get(url: str, retries: int = 3) -> requests.Response:
    for attempt in range(retries):
        time.sleep(0.15)  # stay well under SEC's ~10 req/s fair-access limit
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
            resp.raise_for_status()
            return resp
        time.sleep(2 ** attempt)


def run(tickers: list[str]):
    conn = get_connection()
    try:
        ticker_map = load_ticker_cik_map()

        for ticker in tickers:
            ticker = ticker.upper()
            info = ticker_map.get(ticker)
            if not info:
                print(f"[sec] {ticker}: not found in SEC ticker list, skipping")
                continue

            upsert(
                conn,
                "companies",
                [{"ticker": ticker, "cik": str(info["cik"]), "name": info["name"]}],
                conflict_keys=["ticker"],
            )

            try:
                facts = fetch_company_facts(info["cik"])
            except requests.RequestException as exc:
                print(f"[sec] {ticker}: {exc}")
                continue

            rows = parse_financials(ticker, facts)
            upsert(conn, "financials", rows, conflict_keys=["ticker", "period", "period_type", "accn"])
            print(f"[sec] {ticker}: upserted {len(rows)} financial rows")
    finally:
        conn.close()


if __name__ == "__main__":
    tickers = sys.argv[1:]
    if not tickers:
        print("usage: python -m collector.sec TICKER [TICKER ...]")
        sys.exit(1)
    run(tickers)
