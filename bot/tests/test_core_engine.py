"""Unit tests for bot/core/engine.py enforcing Rules 1-7."""

import pytest
import pandas as pd
from bot.core.data import StockDataClient
from bot.core.engine import BacktestEngine, Instrument


def test_equity_and_futures_sizing():
    engine = BacktestEngine(initial_capital=10_000.0, risk_per_trade_pct=0.01)

    # Equity sizing: $100 risk budget, $2 stop distance -> 50 shares
    inst_eq = Instrument.equity("AAPL")
    shares, achieved_risk = engine.calculate_sizing(inst_eq, entry_price=180.0, stop_price=178.0, equity=10_000.0)
    assert shares == 50.0
    assert abs(achieved_risk - 0.01) < 0.001

    # Futures margin sizing: MES $5/pt multiplier, 10 pt stop = $50 risk per contract.
    # Budget $100 -> 2 contracts
    inst_mes = Instrument.mes()
    contracts, achieved_risk_f = engine.calculate_sizing(inst_mes, entry_price=5000.0, stop_price=4990.0, equity=10_000.0)
    assert contracts == 2.0


def test_rule_4_target_exit_resting_limit_no_slippage():
    """Rule 4: Target exits do NOT slip; stops do slip."""
    engine = BacktestEngine()
    inst = Instrument.equity("SPY", slippage_bps=10.0)  # 10 bps slippage

    # Target exit: 0 slippage
    exit_p, slip = engine.compute_exit_fill(inst, side="long", raw_price=500.0, exit_reason="target")
    assert exit_p == 500.0
    assert slip == 0.0

    # Stop exit: slips by 10 bps = $0.50
    exit_p_stop, slip_stop = engine.compute_exit_fill(inst, side="long", raw_price=490.0, exit_reason="stop")
    assert exit_p_stop < 490.0
    assert slip_stop > 0.0


def test_engine_run_with_ambiguous_bar_resolution():
    """Rule 5: Ambiguous bar resolved pessimistically as stop-first."""
    client = StockDataClient()
    df = client.generate_synthetic_bars("NVDA", "2024-04-01", "2024-04-02")
    engine = BacktestEngine(initial_capital=10_000.0)

    # Manually trigger ambiguous bar by setting stop and target within bar 1's range
    bar1 = df.iloc[1]
    signals = [{
        "entry_idx": 0,
        "side": "long",
        "stop_price": bar1["low"] + 0.01,   # Hit
        "target_price": bar1["high"] - 0.01, # Also hit
        "approved": True,
    }]

    trades = engine.run_strategy(df, "NVDA", signals)
    assert len(trades) == 1
    assert trades[0].was_ambiguous_bar is True
    assert trades[0].exit_reason == "stop"  # Pessimistic resolution
