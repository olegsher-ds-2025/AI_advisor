import numpy as np
import pandas as pd

from quant.indicators import alligator, atr, iix, iix_raw, resample, rsi, supertrend


def bars_from_close(close):
    close = pd.Series(close, index=pd.date_range("2024-01-01", periods=len(close), freq="D"), dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0})


def test_rsi_is_100_in_a_pure_uptrend_and_0_in_a_pure_downtrend():
    assert rsi(bars_from_close(range(1, 40))["close"]).iloc[-1] == 100
    assert rsi(bars_from_close(range(40, 1, -1))["close"]).iloc[-1] == 0


def test_atr_of_constant_range_bars_equals_the_range():
    bars = bars_from_close([10.0] * 30)
    assert atr(bars).iloc[-1] == 2.0


def test_supertrend_follows_the_trend_direction():
    up = supertrend(bars_from_close(np.linspace(10, 100, 60)))
    down = supertrend(bars_from_close(np.linspace(100, 10, 60)))
    assert up["direction"].iloc[-1] == 1
    assert down["direction"].iloc[-1] == -1
    assert up["supertrend"].iloc[-1] < 100
    assert down["supertrend"].iloc[-1] > 10


def test_iix_raw_is_full_volume_when_closing_at_the_high_and_zero_for_flat_bars():
    bars = pd.DataFrame({"open": [1, 5], "high": [2, 5], "low": [1, 5], "close": [2, 5], "volume": [100, 100]})
    assert list(iix_raw(bars)) == [100.0, 0.0]


def test_iix_is_bounded_and_positive_when_closing_at_highs():
    bars = bars_from_close(range(1, 60))
    bars["close"] = bars["high"]
    assert iix(bars).iloc[-1] == 100


def test_alligator_lines_are_shifted_into_the_future():
    bars = bars_from_close(np.linspace(10, 50, 60))
    lines = alligator(bars)
    assert lines["jaw"].first_valid_index() > lines["lips"].first_valid_index()


def test_resample_aggregates_ohlcv():
    bars = bars_from_close(range(1, 15))
    weekly = resample(bars, "W")
    first = weekly.iloc[0]
    assert first["open"] == 1 and first["close"] == 7 and first["high"] == 8 and first["low"] == 0
    assert first["volume"] == 7000
