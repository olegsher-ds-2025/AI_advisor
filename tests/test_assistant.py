import pandas as pd
import pytest
from fastapi.testclient import TestClient

from assistant import app as assistant_app
from assistant import context
from collector import store
from quant.scoring import CATEGORIES


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    context._latest_cached.cache_clear()
    dates = pd.date_range("2024-01-31", periods=6, freq="ME")
    for i, symbol in enumerate(["AAPL", "MSFT", "A"]):
        scores = pd.DataFrame({"symbol": symbol, "as_of": dates, **{c: 50.0 + 10 * i for c in CATEGORIES}, "total": 50.0 + 10 * i})
        store.upsert_symbol("scores", symbol, scores, ["as_of"])
        metrics = pd.DataFrame({"symbol": symbol, "as_of": dates, "pe": 20.0 + i, "roe": 0.3})
        store.upsert_symbol("metrics", symbol, metrics, ["as_of"])
    return tmp_path


def test_find_symbols_needs_known_capitalised_tickers_and_dollar_for_one_letter():
    known = {"AAPL", "MSFT", "A", "IT"}

    assert context.find_symbols("Compare AAPL and MSFT please", known) == ["AAPL", "MSFT"]
    assert context.find_symbols("what is a good stock? Is it cheap", known) == []
    assert context.find_symbols("tell me about $A", known) == ["A"]
    assert context.find_symbols("aapl", known) == []


def test_category_words_pick_the_ranking():
    assert context.find_category("which are the cheapest stocks") == "value"
    assert context.find_category("best quality names") == "quality"
    assert context.find_category("show me something") == "total"


def test_symbol_question_gets_that_symbols_scores_and_factors(lake):
    text = context.build_context("How is MSFT doing?")

    assert "## MSFT" in text and "AAPL" not in text
    assert "- pe: 21.000" in text
    assert "(+0 vs 3m ago)" in text


def test_ranking_question_orders_by_the_category(lake):
    text = context.build_context("top value stocks")

    assert text.startswith("## Top 10 by value")
    assert text.splitlines()[2].split()[0] == "A"


def test_open_webui_task_prompts_are_not_grounded():
    messages = [{"role": "user", "content": "### Task: Generate a title"}]

    assert assistant_app.grounded_messages(messages) == messages


def test_chat_injects_context_and_forwards_to_the_backend(lake, monkeypatch):
    sent = {}

    class Reply:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(assistant_app.requests, "post", lambda url, json, stream, timeout: sent.update(url=url, body=json) or Reply())

    response = TestClient(assistant_app.app).post(
        "/v1/chat/completions", json={"messages": [{"role": "system", "content": "client"}, {"role": "user", "content": "How is MSFT?"}]}
    )

    assert response.json()["choices"][0]["message"]["content"] == "ok"
    assert sent["url"].endswith("/v1/chat/completions")
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]
    assert "## MSFT" in sent["body"]["messages"][0]["content"]
    assert "client" not in sent["body"]["messages"][0]["content"]
