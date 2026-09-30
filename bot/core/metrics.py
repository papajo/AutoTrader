"""Performance analytics and cost waterfall metrics.

Prominently reports:
- Sum of R and Average R (independent of position sizing)
- Target hit rate vs stop out rate
- Expectancy & Profit Factor
- Sharpe & Sortino ratios
- Max Drawdown from daily equity curve
- Cost stack: Pre-cost P&L, slippage, regulatory fees, commission, and Net P&L.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from bot.core.engine import TradeRecord


def compute_metrics(
    trades: List[TradeRecord],
    initial_capital: float = 10000.0,
    risk_free_rate: float = 0.04,
) -> Dict[str, Any]:
    """Compute comprehensive performance and cost metrics from trade records."""
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "target_hit_rate": 0.0,
            "sum_of_r": 0.0,
            "avg_r": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "avg_holding_bars": 0.0,
            "cost_stack": {
                "pnl_pre_cost": 0.0,
                "slippage": 0.0,
                "regulatory_fees": 0.0,
                "commission_fees": 0.0,
                "total_friction": 0.0,
                "pnl_net": 0.0,
            },
            "ambiguous_bars_count": 0,
        }

    n_trades = len(trades)
    pnls_net = np.array([t.pnl_net for t in trades], dtype=float)
    pnls_pre = np.array([t.pnl_pre_cost for t in trades], dtype=float)
    r_multiples = np.array([t.r_multiple for t in trades], dtype=float)
    slippages = np.array([t.slippage_cost for t in trades], dtype=float)
    reg_fees = np.array([t.regulatory_fees for t in trades], dtype=float)
    comm_fees = np.array([t.commission_fees for t in trades], dtype=float)
    holding_bars = np.array([t.holding_bars for t in trades], dtype=float)

    wins = pnls_net > 0
    losses = pnls_net < 0
    target_hits = [t for t in trades if t.exit_reason == "target"]

    win_rate = float(np.mean(wins)) if n_trades > 0 else 0.0
    target_hit_rate = len(target_hits) / n_trades if n_trades > 0 else 0.0

    sum_of_r = float(np.sum(r_multiples))
    avg_r = float(np.mean(r_multiples))

    # Profit factor: gross wins / gross losses
    gross_win = float(np.sum(pnls_net[wins])) if np.any(wins) else 0.0
    gross_loss = abs(float(np.sum(pnls_net[losses]))) if np.any(losses) else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)

    # Expectancy
    avg_win = float(np.mean(pnls_net[wins])) if np.any(wins) else 0.0
    avg_loss = abs(float(np.mean(pnls_net[losses]))) if np.any(losses) else 0.0
    expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss)

    # Equity curve and daily max drawdown
    equity = initial_capital + np.cumsum(pnls_net)
    cummax = np.maximum.accumulate(equity)
    drawdowns = (cummax - equity) / cummax
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Total return & CAGR
    total_net_pnl = float(np.sum(pnls_net))
    ending_capital = initial_capital + total_net_pnl
    total_return_pct = (total_net_pnl / initial_capital) * 100.0

    # Time span for CAGR
    entry_dates = [t.entry_time for t in trades]
    exit_dates = [t.exit_time for t in trades]
    min_date = min(entry_dates)
    max_date = max(exit_dates)
    days = max(1, (max_date - min_date).days)
    years = max(0.01, days / 365.25)
    if ending_capital <= 0:
        cagr_pct = -100.0
    else:
        cagr_pct = float((((ending_capital / initial_capital) ** (1.0 / years)) - 1.0) * 100.0)

    # Sharpe & Sortino (annualized using trade frequency)
    trades_per_year = max(1.0, n_trades / years)
    mean_r = np.mean(r_multiples)
    std_r = np.std(r_multiples, ddof=1) if n_trades > 1 else 1.0
    sharpe = float((mean_r / (std_r if std_r > 0 else 1.0)) * math.sqrt(trades_per_year))

    downside_r = r_multiples[r_multiples < 0]
    downside_std = np.std(downside_r, ddof=1) if len(downside_r) > 1 else std_r
    sortino = float((mean_r / (downside_std if downside_std > 0 else 1.0)) * math.sqrt(trades_per_year))

    # Cost stack
    pnl_pre_cost = float(np.sum(pnls_pre))
    total_slippage = float(np.sum(slippages))
    total_reg_fees = float(np.sum(reg_fees))
    total_comm_fees = float(np.sum(comm_fees))
    total_friction = total_slippage + total_reg_fees + total_comm_fees

    ambiguous_count = sum(1 for t in trades if t.was_ambiguous_bar)

    return {
        "trades": n_trades,
        "win_rate": round(win_rate * 100.0, 1),
        "target_hit_rate": round(target_hit_rate * 100.0, 1),
        "sum_of_r": round(sum_of_r, 3),
        "avg_r": round(avg_r, 4),
        "expectancy_usd": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "max_drawdown_pct": round(max_drawdown * 100.0, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "avg_holding_bars": round(float(np.mean(holding_bars)), 1),
        "cost_stack": {
            "pnl_pre_cost": round(pnl_pre_cost, 2),
            "slippage": round(total_slippage, 2),
            "regulatory_fees": round(total_reg_fees, 2),
            "commission_fees": round(total_comm_fees, 2),
            "total_friction": round(total_friction, 2),
            "pnl_net": round(total_net_pnl, 2),
        },
        "ambiguous_bars_count": ambiguous_count,
    }
