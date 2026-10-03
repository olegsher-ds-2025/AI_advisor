from collector.db import build_upsert


def test_upsert_updates_non_key_columns():
    query = build_upsert("prices", ["ticker", "date", "close"], ["ticker", "date"], False)

    text = repr(query)
    assert "DO UPDATE SET" in text
    assert "EXCLUDED" in text


def test_upsert_does_nothing_when_all_columns_are_keys():
    query = build_upsert("companies", ["ticker"], ["ticker"], False)

    assert "DO NOTHING" in repr(query)
