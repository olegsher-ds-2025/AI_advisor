"""Technical indicators on OHLCV frames (columns open/high/low/close/volume, sorted by time).

Pure pandas, no I/O. Works on any bar size; resample() builds coarser bars from finer ones.
"""
import numpy as np
import pandas as pd

OHLCV_RULES = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    return bars.resample(rule).agg(OHLCV_RULES).dropna(subset=["close"])


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain, loss = _wilder(delta.clip(lower=0), period), _wilder(-delta.clip(upper=0), period)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan)).fillna(np.inf)


def true_range(bars: pd.DataFrame) -> pd.Series:
    prev_close = bars["close"].shift()
    ranges = pd.concat([bars["high"] - bars["low"], (bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()], axis=1)
    return ranges.max(axis=1, skipna=False)


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    return _wilder(true_range(bars), period)


def _smma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def alligator(bars: pd.DataFrame) -> pd.DataFrame:
    median = (bars["high"] + bars["low"]) / 2
    return pd.DataFrame(
        {
            "jaw": _smma(median, 13).shift(8),
            "teeth": _smma(median, 8).shift(5),
            "lips": _smma(median, 5).shift(3),
        }
    )


def supertrend(bars: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Returns the band value and direction (+1 uptrend, -1 downtrend)."""
    mid = (bars["high"] + bars["low"]) / 2
    band = multiplier * atr(bars, period)
    upper_basic, lower_basic = (mid + band).to_numpy(), (mid - band).to_numpy()
    close = bars["close"].to_numpy()

    n = len(bars)
    upper, lower = upper_basic.copy(), lower_basic.copy()
    direction = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(upper_basic[i]):
            continue
        if np.isnan(upper[i - 1]):
            direction[i] = 1 if close[i] >= mid.iloc[i] else -1
            continue
        if upper_basic[i] >= upper[i - 1] and close[i - 1] <= upper[i - 1]:
            upper[i] = upper[i - 1]
        if lower_basic[i] <= lower[i - 1] and close[i - 1] >= lower[i - 1]:
            lower[i] = lower[i - 1]
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] < lower[i] else 1
        else:
            direction[i] = 1 if close[i] > upper[i] else -1

    value = np.where(direction == 1, lower, np.where(direction == -1, upper, np.nan))
    return pd.DataFrame({"supertrend": value, "direction": direction}, index=bars.index)


def iix_raw(bars: pd.DataFrame) -> pd.Series:
    spread = (bars["high"] - bars["low"]).replace(0, np.nan)
    return ((2 * bars["close"] - bars["high"] - bars["low"]) / spread * bars["volume"]).fillna(0)


def iix(bars: pd.DataFrame, period: int = 21) -> pd.Series:
    """Intraday Intensity Index: rolling sum of raw bar values, normalised by rolling volume (range -100..100)."""
    volume = bars["volume"].rolling(period).sum().replace(0, np.nan)
    return 100 * iix_raw(bars).rolling(period).sum() / volume
