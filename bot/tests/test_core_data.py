"""Unit tests for bot/core/data.py."""

import pytest
import pandas as pd
from bot.core.data import StockDataClient, BARS_PER_REGULAR_DAY_5M


def test_synthetic_data_generation_and_78_bars():
    client = StockDataClient()
    df = client.fetch_bars("AAPL", "2024-01-08", "2024-01-12", use_cache=False)
    
    assert not df.empty
    is_valid, counts = client.verify_bars_per_day(df)
    assert is_valid is True
    # 5 business days, each exactly 78 bars
    assert len(counts) == 5
    for dt, count in counts.items():
        assert count == BARS_PER_REGULAR_DAY_5M


def test_regular_session_filtering():
    client = StockDataClient()
    df = client.generate_synthetic_bars("SPY", "2024-02-01", "2024-02-02")
    filtered = client.filter_regular_session(df)
    
    # Assert time bounds strictly within 09:30 and 15:55
    min_time = filtered.index.time.min()
    max_time = filtered.index.time.max()
    assert min_time >= pd.to_datetime("09:30").time()
    assert max_time <= pd.to_datetime("15:55").time()
