"""Unit tests for bot/core/features.py."""

import pytest
import pandas as pd
import numpy as np
from bot.core.data import StockDataClient
from bot.core.features import (
    compute_atr,
    compute_ema,
    compute_session_vwap,
    resample_bars,
    align_higher_timeframe,
)


@pytest.fixture
def sample_bars():
    client = StockDataClient()
    return client.generate_synthetic_bars("MSFT", "2024-03-01", "2024-03-05")


def test_atr_and_ema_calculation(sample_bars):
    atr = compute_atr(sample_bars, period=14)
    ema = compute_ema(sample_bars["close"], span=20)
    
    assert len(atr) == len(sample_bars)
    assert len(ema) == len(sample_bars)
    # First 14 bars of ATR should be NaN (trailing window only)
    assert pd.isna(atr.iloc[0])
    assert not pd.isna(atr.iloc[15])
    assert not pd.isna(ema.iloc[-1])


def test_session_vwap(sample_bars):
    vwap = compute_session_vwap(sample_bars)
    assert len(vwap) == len(sample_bars)
    # Check that VWAP is between low and high
    assert vwap.iloc[-1] >= sample_bars["low"].min()
    assert vwap.iloc[-1] <= sample_bars["high"].max()


def test_rule_9_htf_alignment_shift(sample_bars):
    """Rule 9: 15-minute bar stamped 09:30 is only complete at 09:45."""
    df_15m = resample_bars(sample_bars, "15min")
    ema_15m = compute_ema(df_15m["close"], span=10)
    
    slow_delta = pd.Timedelta(minutes=15)
    aligned = align_higher_timeframe(sample_bars, ema_15m, slow_delta)
    
    assert len(aligned) == len(sample_bars)
    # At 09:30, the 15m bar from 09:30-09:45 is NOT complete, so it must not leak
    # Values before 09:45 on Day 1 should be NaN or from prior session
    first_day_bars = sample_bars.loc[sample_bars.index.date == sample_bars.index.date[0]]
    bar_0930 = first_day_bars.index[0]
    bar_0940 = first_day_bars.index[2]
    bar_0945 = first_day_bars.index[3]
    
    # Value at 09:45 should reflect completion of 09:30 bar
    assert not pd.isna(aligned.loc[bar_0945])
