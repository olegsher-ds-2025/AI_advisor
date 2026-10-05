"""Fetches every concept collector.financials maps straight from SEC companyfacts and stores them in
the same long format as advisor/facts_extra/, which collector.financials merges with the lake's
fundamentals/ facts. It covers what the lake lacks (cash flow, gross profit, operating income) and
the delisted ex-index members from collector.membership, which the lake never collected.

Usage:
    python -m collector.sec_facts              # lake symbols + ex-index members
    python -m collector.sec_facts AAPL MSFT
"""
import argparse
import json
import time
import urllib.request

import pandas as pd

from collector.financials import CONCEPT_MAP
from collector.membership import tracked_symbols
from collector.store import upsert_symbol

USER_AGENT = "Oleg Sher olegsher-ds-2025@sher.biz"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CONCEPTS = list(CONCEPT_MAP)
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
KEYS = ["concept", "period_start", "period_end", "accession_no"]
REQUEST_GAP_SECONDS = 0.15  # SEC allows 10 requests/s


def _get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def ticker_to_cik() -> dict[str, int]:
    return {row["ticker"]: row["cik_str"] for row in _get(TICKERS_URL).values()}


def extract_facts(company_facts: dict) -> pd.DataFrame:
    rows = []
    gaap = company_facts.get("facts", {}).get("us-gaap", {})
    for concept in CONCEPTS:
        for unit, entries in gaap.get(concept, {}).get("units", {}).items():
            rows += [
                (concept, e["val"], unit, e.get("start"), e["end"], e["form"], e["filed"], e["accn"])
                for e in entries
                if e["form"] in FORMS
            ]
    return pd.DataFrame(
        rows, columns=["concept", "value", "unit", "period_start", "period_end", "form", "filed_at", "accession_no"]
    )


def run(symbols: list[str]):
    ciks = ticker_to_cik()
    for symbol in symbols:
        symbol = symbol.upper()
        cik = ciks.get(symbol) or ciks.get(symbol.replace("-", "."))
        if cik is None:
            print(f"[sec_facts] {symbol}: no CIK, skipping")
            continue
        try:
            facts = extract_facts(_get(FACTS_URL.format(cik=cik)))
        except OSError as error:
            print(f"[sec_facts] {symbol}: {error}, skipping")
            continue
        if facts.empty:
            print(f"[sec_facts] {symbol}: no us-gaap facts (foreign filer?), skipping")
            continue
        path = upsert_symbol("facts_extra", symbol, facts, KEYS)
        print(f"[sec_facts] {symbol}: {len(facts)} facts -> {path}")
        time.sleep(REQUEST_GAP_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    run(parser.parse_args().symbols or tracked_symbols())
