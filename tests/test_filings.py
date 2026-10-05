import pandas as pd
import pytest

from ai import rag
from collector import filings, store


def test_latest_filings_keeps_the_newest_10k_and_10q_only():
    submissions = {"filings": {"recent": {
        "form": ["8-K", "10-Q", "10-K", "10-Q", "10-K"],
        "accessionNumber": ["a1", "a2", "a3", "a4", "a5"],
        "filingDate": ["2024-05-02", "2024-05-01", "2024-02-01", "2023-11-01", "2023-02-01"],
        "primaryDocument": ["d1", "d2", "d3", "d4", "d5"],
    }}}

    assert [(f["form"], f["accn"]) for f in filings.latest_filings(submissions)] == [("10-Q", "a2"), ("10-K", "a3")]


def test_chunks_follow_the_last_item_heading_and_drop_unkept_items(monkeypatch):
    monkeypatch.setattr(filings, "MIN_CHUNK_CHARS", 0)
    lines = [
        "Item 1. Business", "We make widgets.",
        "Item 1A. Risk Factors", "Supply chains may fail.",
        "Item 8. Financial Statements", "Notes to statements.",
        "Item 7. Management's Discussion", "Revenue grew.",
    ]

    chunks = filings.chunk_filing(lines, "10-K")

    assert [item for item, _ in chunks] == ["1", "1A", "7"]
    assert "Supply chains may fail." in chunks[1][1] and "Notes to statements." not in " ".join(t for _, t in chunks)


def test_short_chunks_such_as_table_of_contents_lines_are_dropped():
    assert filings.chunk_filing(["Item 1A. Risk Factors 12", "Item 7. MD&A 40"], "10-K") == []


def test_prose_starting_with_item_is_not_a_heading():
    prose = "Item 8 of this report contains the financial statements and supplementary data " + "x" * 100

    assert [i for i, _ in filings.chunk_filing(["Item 1A. Risk Factors", "r" * 300, prose], "10-K")] == ["1A"]


def test_document_lines_drop_hidden_xbrl_and_keep_block_structure():
    raw = b"<html><body><ix:header>us-gaap:Revenue 5</ix:header><div>Item 1A. Risk Factors</div><div>Tariffs hurt us.</div><table><tr><td>a</td><td>b</td></tr></table></body></html>"

    assert filings.document_lines(raw) == ["Item 1A. Risk Factors", "Tariffs hurt us.", "a b"]


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    rows = pd.DataFrame({
        "symbol": "AAPL", "accn": "a", "form": "10-K", "filed": pd.Timestamp("2025-10-31"), "item": ["1A", "1A", "7"],
        "chunk": [0, 1, 2],
        "text": ["Tariffs on imported components could raise our costs.", "Our stock price may be volatile.", "Services revenue grew."],
    })
    store.upsert_symbol("filings", "AAPL", rows, ["accn", "chunk"])


def test_retrieve_ranks_chunks_by_term_overlap(lake):
    found = rag.retrieve("AAPL", "what tariff risks does it have?", k=2)

    assert found["text"].iloc[0].startswith("Tariffs")


def test_retrieve_returns_nothing_without_a_match_or_filings(lake):
    assert rag.retrieve("AAPL", "zebra", k=2).empty
    assert rag.retrieve("MSFT", "tariffs", k=2).empty
