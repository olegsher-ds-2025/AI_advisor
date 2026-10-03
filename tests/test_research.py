import pytest

from ai.research import build_prompt, parse_note
from collector.store import DATA_DIR


def test_parse_note_extracts_json_wrapped_in_prose():
    text = 'Here you go:\n```json\n{"thesis": "T", "bull_case": "B", "risks": "R"}\n```'

    note = parse_note(text)

    assert note["thesis"] == "T" and note["risks"] == "R"
    assert note["bear_case"] is None and note["raw"] == text


def test_parse_note_keeps_raw_text_when_not_json():
    note = parse_note("no json here")

    assert note["thesis"] is None and note["raw"] == "no json here"


@pytest.mark.skipif(not (DATA_DIR / "scores").exists(), reason="needs the advisor parquet lake")
def test_prompt_is_built_from_real_data_and_forbids_advice():
    prompt = build_prompt("AAPL")

    assert "AAPL" in prompt and "Never give buy/sell/hold advice" in prompt
    assert "- total:" in prompt and "{symbol}" not in prompt
