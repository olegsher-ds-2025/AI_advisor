"""Latest 10-K and 10-Q text from SEC EDGAR, cut into chunks for retrieval (ai/rag.py).

Only the sections that carry the story are kept: 10-K Items 1 (business), 1A (risk factors),
7 (MD&A), 7A; 10-Q Items 2 (MD&A) and 1A. Financial statement notes are skipped, the numbers
already live in `financials`. One parquet per symbol in advisor/filings/, one row per chunk.

Usage:
    python -m collector.filings AAPL MSFT       # no args = every symbol in the lake
"""
import argparse
import re
import time
import urllib.request

import pandas as pd
from lxml import html as lxml_html

from collector.sec_facts import USER_AGENT, _get, ticker_to_cik
from collector.store import source_symbols, upsert_symbol

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}"
KEPT_ITEMS = {"10-K": {"1", "1A", "7", "7A"}, "10-Q": {"2", "1A"}}
CHUNK_CHARS = 1500
MIN_CHUNK_CHARS = 200  # shorter chunks are table-of-contents lines and stray headings
ITEM = re.compile(r"^item\s*(\d{1,2}[AB]?)\b\.?", re.I)
HEADING_MAX_CHARS = 150  # longer lines that start with "Item" are prose, not headings
BLOCK_TAGS = ("p", "div", "tr", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table")
REQUEST_GAP_SECONDS = 0.15


def fetch_html(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def latest_filings(submissions: dict) -> list[dict]:
    """The most recent 10-K and 10-Q."""
    recent = submissions["filings"]["recent"]
    found = {}
    for form, accn, filed, doc in zip(recent["form"], recent["accessionNumber"], recent["filingDate"], recent["primaryDocument"]):
        if form in KEPT_ITEMS and form not in found:
            found[form] = {"form": form, "accn": accn, "filed": filed, "doc": doc}
    return list(found.values())


def document_lines(raw: bytes) -> list[str]:
    doc = lxml_html.fromstring(raw)
    for el in doc.xpath("//script | //style | //*[starts-with(name(), 'ix:header')]"):
        el.drop_tree()
    for el in doc.iter(*BLOCK_TAGS):
        el.tail = "\n" + (el.tail or "")
    for el in doc.iter("td", "th"):
        el.tail = " " + (el.tail or "")
    lines = (re.sub(r"\s+", " ", line).strip() for line in doc.text_content().split("\n"))
    return [line for line in lines if line]


def chunk_filing(lines: list[str], form: str) -> list[tuple[str, str]]:
    """(item, text) chunks of the kept items. The last "Item X" line seen names the section, so a table
    of contents is overridden as soon as the real heading appears."""
    chunks, item, buffer = [], None, []

    def flush():
        text = " ".join(buffer)
        if item in KEPT_ITEMS[form] and len(text) >= MIN_CHUNK_CHARS:
            chunks.append((item, text))
        buffer.clear()

    for line in lines:
        match = ITEM.match(line) if len(line) <= HEADING_MAX_CHARS else None
        if match:
            flush()
            item = match.group(1).upper()
        buffer.append(line)
        if sum(map(len, buffer)) >= CHUNK_CHARS:
            flush()
    flush()
    return chunks


def build_rows(symbol: str, filing: dict, chunks: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": symbol, "accn": filing["accn"], "form": filing["form"], "filed": pd.Timestamp(filing["filed"]),
             "item": item, "chunk": i, "text": text}
            for i, (item, text) in enumerate(chunks)
        ]
    )


def run(symbols: list[str]):
    ciks = ticker_to_cik()
    for symbol in symbols:
        symbol = symbol.upper()
        cik = ciks.get(symbol) or ciks.get(symbol.replace("-", "."))
        if cik is None:
            print(f"[filings] {symbol}: no CIK, skipping")
            continue
        try:
            frames = []
            for filing in latest_filings(_get(SUBMISSIONS_URL.format(cik=cik))):
                url = DOC_URL.format(cik=cik, accn=filing["accn"].replace("-", ""), doc=filing["doc"])
                frames.append(build_rows(symbol, filing, chunk_filing(document_lines(fetch_html(url)), filing["form"])))
                time.sleep(REQUEST_GAP_SECONDS)
        except OSError as error:
            print(f"[filings] {symbol}: {error}, skipping")
            continue
        rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if rows.empty:
            print(f"[filings] {symbol}: no 10-K/10-Q text found, skipping")
            continue
        path = upsert_symbol("filings", symbol, rows, ["accn", "chunk"])
        print(f"[filings] {symbol}: {len(rows)} chunks ({', '.join(sorted(set(rows['form'])))}) -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    run(parser.parse_args().symbols or source_symbols())
