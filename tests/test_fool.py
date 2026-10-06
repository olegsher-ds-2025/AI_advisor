import numpy as np
import pandas as pd
import pytest

from fool import combine, features, ingest


def test_parse_market_cap():
    assert ingest.parse_market_cap("$152B") == 152e9
    assert ingest.parse_market_cap("$177M") == 177e6
    assert pd.isna(ingest.parse_market_cap("N/A Stock quote details"))


def test_merge_matches_renamed_tickers(tmp_path, monkeypatch):
    xlsx = pd.DataFrame({"rec_date": [pd.Timestamp("2015-02-20")], "company": ["FireEye"], "ticker_raw": ["FEYE"], "ticker": ["FEYE"],
                         "delisted": [False], "closed_date": [pd.NaT], "market_cap": [1.0], "team": ["Tom"], "risk_rating": [None],
                         "rec_price": [30.0], "return": [0.5], "spx_return": [0.2], "excess_return": [0.3], "price_unavailable": [False]})
    new = pd.DataFrame({"date": [pd.Timestamp("2015-02-20"), pd.Timestamp("2020-05-20")], "symbol": ["MNDT", "MNDT"],
                        "name": ["Mandiant"] * 2, "recommendation": ["BUY", "SELL"]})
    xlsx.to_parquet(tmp_path / "picks_returns.parquet")
    new.to_parquet(tmp_path / "newrecs.parquet")
    monkeypatch.setattr(combine, "FOOL_DIR", tmp_path)
    df = combine.merge_sources()
    assert df["source"].tolist() == ["both", "newrecs"]
    assert df["symbol"].tolist() == ["MNDT", "MNDT"]
    assert df["ticker_at_rec"].tolist() == ["FEYE", "MNDT"]


def _series(n=800, start="2018-01-01", growth=0.001):
    idx = pd.bdate_range(start, periods=n)
    adj = 100 * (1 + growth) ** np.arange(n)
    return pd.DataFrame({"close": adj, "adj_close": adj}, index=idx)


def test_price_features_use_only_past_data():
    px = _series()
    t = px.index[500]
    base = features.price_features(px, px, t)
    changed = px.copy()
    changed.loc[changed.index > t, "adj_close"] *= 10
    assert features.price_features(changed, px, t) == base
    assert base["ret_1m"] == pytest.approx(1.001 ** 21 - 1)
    assert base["rel_ret_3m"] == pytest.approx(0)


def test_price_features_need_history():
    px = _series()
    assert features.price_features(px, px, px.index[100]) == {}


def test_controls_exclude_picked_symbols():
    series = {s: _series() for s in ["AAA", "BBB", "CCC", "SPY"]}
    picks = pd.DataFrame({"rec_date": [pd.Timestamp("2020-06-01")], "symbol": ["AAA"], "yf_symbol": ["AAA"]})
    controls = features.sample_controls(picks, series)
    assert set(controls["symbol"]) == {"BBB", "CCC"}


def test_raw_close_undoes_later_splits():
    from fool import pit

    px = _series(300)
    splits = {"X": pd.Series([4.0, 2.0], index=[px.index[200], px.index[250]])}
    assert pit.raw_close(px, splits, "X", px.index[100]) == pytest.approx(px["close"].iloc[100] * 8)
    assert pit.raw_close(px, splits, "X", px.index[220]) == pytest.approx(px["close"].iloc[220] * 2)
    assert pit.raw_close(px, splits, "X", px.index[280]) == pytest.approx(px["close"].iloc[280])
