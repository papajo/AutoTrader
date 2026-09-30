"""Feature engineering with trailing-only calculations and causal HTF alignment.

Strictly adheres to:
- Rule 8: Never render missing indicator as 0.0 (return None/NaN so caller can drop).
- Rule 9: Higher-timeframe values must be shifted forward one of their own bars before reindexing.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range using strictly trailing window (Wilder's smoothing)."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)
    
    if n < period + 1:
        return pd.Series(index=df.index, dtype=float)

    tr = np.zeros(n, dtype=float)
    tr[0] = high[0] - low[0]
    
    for i in range(1, n):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i - 1])
        l_pc = abs(low[i] - close[i - 1])
        tr[i] = max(h_l, h_pc, l_pc)

    atr = np.full(n, np.nan, dtype=float)
    atr[period] = np.mean(tr[1:period + 1])
    
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return pd.Series(atr, index=df.index, name=f"atr_{period}")


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Compute Exponential Moving Average using strictly trailing exponential weights."""
    return series.ewm(span=span, adjust=False).mean()


def compute_session_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute Volume Weighted Average Price resetting at the start of each trading session."""
    # Group by date in the timestamp index
    df_copy = df[["high", "low", "close", "volume"]].copy()
    typical_price = (df_copy["high"] + df_copy["low"] + df_copy["close"]) / 3.0
    tp_vol = typical_price * df_copy["volume"]

    # Identify session boundary (change in date)
    date_col = pd.Series(df.index.date, index=df.index)
    session_id = (date_col != date_col.shift(1)).cumsum()

    cum_tp_vol = tp_vol.groupby(session_id).cumsum()
    cum_vol = df_copy["volume"].groupby(session_id).cumsum()

    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    return pd.Series(vwap, index=df.index, name="session_vwap")


def resample_bars(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample 5-minute bars to higher timeframe (e.g. '15min', '1h', '1D')."""
    resampled = df.resample(freq, closed="left", label="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return resampled


def align_higher_timeframe(
    fast_df: pd.DataFrame,
    slow_series: pd.Series,
    slow_bar_delta: pd.Timedelta,
) -> pd.Series:
    """Higher-timeframe alignment helper implementing Rule 9.

    Rule 9: Higher-timeframe values must be shifted forward one of their own bars
    before reindexing onto a faster series. A 15-minute bar stamped 09:30 is only
    complete at 09:45.

    Args:
        fast_df: 5-minute DataFrame with DatetimeIndex
        slow_series: Series computed on higher timeframe (e.g. 15-minute EMA)
        slow_bar_delta: Duration of the slow bar (e.g. pd.Timedelta(minutes=15))

    Returns:
        pd.Series aligned to fast_df.index with no lookahead bias.
    """
    # Shift timestamp forward by the duration of the slow bar so its values only
    # become available at the exact bar close.
    shifted_slow = slow_series.copy()
    shifted_slow.index = shifted_slow.index + slow_bar_delta

    # Reindex onto fast_df timestamps using forward-fill
    aligned = shifted_slow.reindex(fast_df.index, method="ffill")
    return aligned
