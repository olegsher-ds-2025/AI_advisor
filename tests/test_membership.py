import pandas as pd

from collector import membership


def test_filter_members_keeps_rows_inside_a_membership_spell(tmp_path, monkeypatch):
    spells = pd.DataFrame({
        "symbol": ["A", "B", "B"],
        "start": pd.to_datetime(["2020-01-01", "2010-01-01", "2022-06-01"]),
        "end": pd.to_datetime([None, "2021-01-01", None]),
    })
    monkeypatch.setattr(membership, "read_membership", lambda: spells)
    df = pd.DataFrame({
        "symbol": ["A", "A", "B", "B", "B", "C"],
        "as_of": pd.to_datetime(["2019-12-31", "2020-01-31", "2020-06-30", "2021-01-01", "2022-06-30", "2020-06-30"]),
    })

    kept = membership.filter_members(df)

    assert kept[["symbol", "as_of"]].astype(str).values.tolist() == [
        ["A", "2020-01-31"], ["B", "2020-06-30"], ["B", "2022-06-30"],
    ]


def test_filter_members_is_a_no_op_without_a_membership_file(monkeypatch):
    def missing():
        raise FileNotFoundError

    monkeypatch.setattr(membership, "read_membership", missing)
    df = pd.DataFrame({"symbol": ["A"], "as_of": pd.to_datetime(["2020-01-31"])})

    assert membership.filter_members(df).equals(df)
