"""Unit and integration tests for all 6 trading strategies."""

import pytest
import pandas as pd
from bot.core.data import StockDataClient
from bot.strategies.orb import ORBStrategy
from bot.strategies.insider import InsiderTradingStrategy, SECForm4Parser
from bot.strategies.earnings_drift import PostEarningsDriftStrategy, SEC8KParser
from bot.strategies.overnight_futures import OvernightFuturesStrategy
from bot.strategies.news_scalp import NewsScalpStrategy
from bot.strategies.lunar_gann import LunarPhaseStrategy, LunarEphemeris


@pytest.fixture
def market_data():
    client = StockDataClient()
    return {
        "SPY": client.generate_synthetic_bars("SPY", "2023-01-01", "2023-04-01", base_price=450.0),
        "AAPL": client.generate_synthetic_bars("AAPL", "2023-01-01", "2023-04-01", base_price=175.0),
        "MES": client.generate_synthetic_bars("MES", "2023-01-01", "2023-01-10", base_price=4800.0),
        "MNQ": client.generate_synthetic_bars("MNQ", "2023-01-01", "2023-01-10", base_price=16000.0),
        "M2K": client.generate_synthetic_bars("M2K", "2023-01-01", "2023-01-10", base_price=2000.0),
        "MYM": client.generate_synthetic_bars("MYM", "2023-01-01", "2023-01-10", base_price=38000.0),
    }


def test_agent_1_orb_strategy(market_data):
    orb = ORBStrategy()
    res = orb.run_all_three_arms("SPY", start_date="2023-01-01", end_date="2023-04-01")
    assert "rules" in res
    assert "gated" in res
    assert "jev" in res
    assert res["rules"]["metrics"]["trades"] >= 0


def test_agent_2_insider_strategy(market_data):
    events = SECForm4Parser.generate_synthetic_purchases(["AAPL"], start_year=2023, end_year=2023, n_events=10)
    strategy = InsiderTradingStrategy(k_slots=5, holding_days=5)
    book_res = strategy.run_marked_to_market_book(events, {"AAPL": market_data["AAPL"]}, market_data["SPY"])
    assert "final_equity" in book_res
    assert "cagr_pct" in book_res


def test_agent_3_earnings_drift_strategy(market_data):
    events = SEC8KParser.generate_synthetic_earnings_events(["AAPL"], start_year=2023, end_year=2023)
    pead = PostEarningsDriftStrategy(holding_sessions=5, min_gap_pct=0.01)
    res = pead.run_strategy(events, {"AAPL": market_data["AAPL"]}, market_data["SPY"])
    assert "trades_count" in res
    assert "profit_factor" in res


def test_agent_4_overnight_futures_strategy(market_data):
    futures_data = {
        "MES": market_data["MES"],
        "MNQ": market_data["MNQ"],
        "M2K": market_data["M2K"],
        "MYM": market_data["MYM"],
    }
    strategy = OvernightFuturesStrategy()
    res = strategy.run_strategy(futures_data)
    assert "all_sessions" in res
    assert "asia_only" in res


def test_agent_5_news_scalp_strategy(market_data):
    events = SEC8KParser.generate_synthetic_earnings_events(["AAPL"], start_year=2023, end_year=2023)
    scalp = NewsScalpStrategy()
    cands = scalp.extract_scalp_candidates(events, {"AAPL": market_data["AAPL"]})
    res = scalp.run_strategy(cands, {"AAPL": market_data["AAPL"]})
    assert "rules" in res
    assert "gated" in res
    assert "jev" in res


def test_agent_6_lunar_gann_strategy(market_data):
    daily_spy = market_data["SPY"].resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    lunar = LunarPhaseStrategy()
    scan_res = lunar.run_shift_scan(daily_spy, "SPY", n_shifts=5)
    assert "true_calendar_rank" in scan_res
    assert len(scan_res["all_shifts"]) == 5
