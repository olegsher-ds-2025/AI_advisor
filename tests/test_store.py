import pandas as pd

from collector import store


def test_upsert_symbol_replaces_duplicate_keys_and_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store.upsert_symbol("prices", "AAPL", pd.DataFrame({"date": [1, 2], "close": [10.0, 20.0]}), ["date"])

    path = store.upsert_symbol("prices", "AAPL", pd.DataFrame({"date": [2, 3], "close": [21.0, 30.0]}), ["date"])

    assert path == tmp_path / "prices" / "symbol=AAPL" / "prices.parquet"
    assert pd.read_parquet(path)["close"].tolist() == [10.0, 21.0, 30.0]


def test_clean_news_splits_the_provider_tag_and_drops_empty_headlines():
    from collector.store import clean_news

    news = pd.DataFrame({"headline": [
        "{A:800015:L:en:K:-0.97:C:0.97}!Evercore ISI downgraded Halliburton (HAL) to In-line",
        "{A:800015:L:en}Apple &amp; friends rally",
        "{A:800015:L:en:K:0.97:C:0.97}!",
    ]})

    cleaned = clean_news(news)

    assert cleaned["headline"].tolist() == ["Evercore ISI downgraded Halliburton (HAL) to In-line", "Apple & friends rally"]
    assert cleaned["sentiment"].tolist()[0] == -0.97 and pd.isna(cleaned["sentiment"].tolist()[1])
