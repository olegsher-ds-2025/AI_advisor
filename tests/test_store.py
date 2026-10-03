import pandas as pd

from collector import store


def test_upsert_symbol_replaces_duplicate_keys_and_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    store.upsert_symbol("prices", "AAPL", pd.DataFrame({"date": [1, 2], "close": [10.0, 20.0]}), ["date"])

    path = store.upsert_symbol("prices", "AAPL", pd.DataFrame({"date": [2, 3], "close": [21.0, 30.0]}), ["date"])

    assert path == tmp_path / "prices" / "symbol=AAPL" / "prices.parquet"
    assert pd.read_parquet(path)["close"].tolist() == [10.0, 21.0, 30.0]
