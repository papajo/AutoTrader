"""Prompt 3: Post-Earnings Announcement Drift (PEAD) Strategy on Mega Caps.

Hedging each earnings position 1:1 against SPY with 10-day holds and notional sizing.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.strategies.earnings_drift.parser import EarningsEvent, SEC8KParser


@dataclass
class HedgedPEADTrade:
    """A pair trade holding the earnings gap stock and shorting an equal notional of SPY."""
    ticker: str
    entry_date: date
    exit_date: date
    gap_direction: str  # 'long' if gap up, 'short' if gap down
    gap_pct: float
    stock_entry_price: float
    stock_exit_price: float
    spy_entry_price: float
    spy_exit_price: float
    notional: float
    pnl_stock: float
    pnl_spy_hedge: float
    pnl_net: float
    return_pct: float
    hit_disaster_stop: bool = False


class PostEarningsDriftStrategy:
    """Post-Earnings Announcement Drift on 40 Mega-Caps, hedged against SPY."""

    def __init__(
        self,
        holding_sessions: int = 10,
        min_gap_pct: float = 0.05,  # 5% gap threshold
        notional_pct_per_trade: float = 0.05,  # 5% of portfolio equity per event
        disaster_stop_gap_multiple: float = 3.0,
    ):
        self.holding_sessions = holding_sessions
        self.min_gap_pct = min_gap_pct
        self.notional_pct_per_trade = notional_pct_per_trade
        self.disaster_stop_gap_multiple = disaster_stop_gap_multiple

    def run_event_study(
        self,
        events: List[EarningsEvent],
        price_data: Dict[str, pd.DataFrame],
        spy_df: pd.DataFrame,
        horizons: Tuple[int, ...] = (1, 5, 10, 20, 40),
    ) -> Dict[str, Any]:
        """Event study measuring sign-adjusted forward returns excess of SPY across gap thresholds."""
        records = []
        spy_daily = spy_df.resample("1D").agg({"open": "first", "close": "last"}).dropna()

        for ev in events:
            df = price_data.get(ev.ticker)
            if df is None or df.empty:
                continue

            daily = df.resample("1D").agg({"open": "first", "close": "last"}).dropna()
            tradable_bars = daily.loc[daily.index.date >= ev.first_tradable_date]
            prior_bars = daily.loc[daily.index.date < ev.first_tradable_date]

            if tradable_bars.empty or prior_bars.empty or len(tradable_bars) < max(horizons):
                continue

            prior_close = prior_bars.iloc[-1]["close"]
            entry_open = tradable_bars.iloc[0]["open"]
            gap_pct = (entry_open - prior_close) / prior_close

            # Direction of gap: +1 for gap up (long), -1 for gap down (short)
            direction_sign = 1.0 if gap_pct > 0 else -1.0
            abs_gap = abs(gap_pct)

            # Benchmark at entry
            entry_date = tradable_bars.index[0].date()
            spy_forward = spy_daily.loc[spy_daily.index.date >= entry_date]
            if len(spy_forward) < max(horizons):
                continue
            spy_entry_open = spy_forward.iloc[0]["open"]

            row = {
                "ticker": ev.ticker,
                "date": entry_date,
                "gap_pct": gap_pct,
                "abs_gap_pct": abs_gap,
            }

            for h in horizons:
                exit_close = tradable_bars.iloc[h - 1]["close"]
                ret_stock = (exit_close - entry_open) / entry_open

                spy_exit_close = spy_forward.iloc[h - 1]["close"]
                ret_spy = (spy_exit_close - spy_entry_open) / spy_entry_open

                excess = ret_stock - ret_spy
                # Sign-adjust: If gap down, we short the stock and buy SPY
                sign_adjusted_excess = excess * direction_sign
                row[f"excess_{h}d"] = sign_adjusted_excess

            records.append(row)

        df_study = pd.DataFrame(records)
        results = {}

        for threshold_name, min_gap in [("all_gaps_0.5pct", 0.005), ("gaps_ge_5pct", 0.05)]:
            subset = df_study[df_study["abs_gap_pct"] >= min_gap]
            horizon_stats = {}
            for h in horizons:
                col = f"excess_{h}d"
                vals = subset[col].dropna().values
                if len(vals) > 0:
                    mean_val = float(np.mean(vals))
                    std_val = float(np.std(vals, ddof=1)) if len(vals) > 1 else 1.0
                    t_stat = (mean_val / (std_val / math.sqrt(len(vals)))) if len(vals) > 1 else 0.0
                    horizon_stats[f"{h}d"] = {
                        "n": len(vals),
                        "mean_pct": round(mean_val * 100.0, 2),
                        "t_stat": round(t_stat, 2),
                    }
            results[threshold_name] = horizon_stats

        return {"event_study": results, "total_events": len(records)}

    def run_strategy(
        self,
        events: List[EarningsEvent],
        price_data: Dict[str, pd.DataFrame],
        spy_df: pd.DataFrame,
        initial_capital: float = 100_000.0,
    ) -> Dict[str, Any]:
        """Execute the 10-day hedged PEAD trading book sized by notional."""
        trades: List[HedgedPEADTrade] = []
        spy_daily = spy_df.resample("1D").agg({"open": "first", "close": "last"}).dropna()

        for ev in events:
            df = price_data.get(ev.ticker)
            if df is None or df.empty:
                continue

            daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
            tradable_bars = daily.loc[daily.index.date >= ev.first_tradable_date]
            prior_bars = daily.loc[daily.index.date < ev.first_tradable_date]

            if tradable_bars.empty or prior_bars.empty or len(tradable_bars) < self.holding_sessions:
                continue

            prior_close = prior_bars.iloc[-1]["close"]
            entry_open = tradable_bars.iloc[0]["open"]
            gap_pct = (entry_open - prior_close) / prior_close

            # Filter by minimum gap threshold (e.g. >= 5%)
            if abs(gap_pct) < self.min_gap_pct:
                continue

            direction = "long" if gap_pct > 0 else "short"
            notional = initial_capital * self.notional_pct_per_trade

            entry_date = tradable_bars.index[0].date()
            spy_forward = spy_daily.loc[spy_daily.index.date >= entry_date]
            if len(spy_forward) < self.holding_sessions:
                continue
            spy_entry_open = spy_forward.iloc[0]["open"]

            # Disaster stop: 3 gap widths away
            gap_width = abs(entry_open - prior_close)
            disaster_stop = (entry_open - self.disaster_stop_gap_multiple * gap_width) if direction == "long" else (
                entry_open + self.disaster_stop_gap_multiple * gap_width
            )

            # Check if disaster stop was hit over holding period
            exit_idx = self.holding_sessions - 1
            hit_stop = False
            for d in range(self.holding_sessions):
                bar = tradable_bars.iloc[d]
                if direction == "long" and bar["low"] <= disaster_stop:
                    exit_idx = d
                    hit_stop = True
                    break
                elif direction == "short" and bar["high"] >= disaster_stop:
                    exit_idx = d
                    hit_stop = True
                    break

            exit_date = tradable_bars.index[exit_idx].date()
            stock_exit = disaster_stop if hit_stop else tradable_bars.iloc[exit_idx]["open"]
            spy_exit = spy_forward.iloc[exit_idx]["open"]

            # P&L calculations
            if direction == "long":
                ret_stock = (stock_exit - entry_open) / entry_open
                ret_spy = (spy_exit - spy_entry_open) / spy_entry_open
            else:
                ret_stock = (entry_open - stock_exit) / entry_open
                ret_spy = (spy_entry_open - spy_exit) / spy_entry_open

            pnl_stock = notional * ret_stock
            pnl_spy = -notional * ret_spy  # Short SPY hedge
            pnl_net = pnl_stock + pnl_spy - 0.45  # $0.45 friction per event on 10-day hold

            trades.append(HedgedPEADTrade(
                ticker=ev.ticker,
                entry_date=entry_date,
                exit_date=exit_date,
                gap_direction=direction,
                gap_pct=round(gap_pct * 100.0, 2),
                stock_entry_price=round(entry_open, 2),
                stock_exit_price=round(stock_exit, 2),
                spy_entry_price=round(spy_entry_open, 2),
                spy_exit_price=round(spy_exit, 2),
                notional=notional,
                pnl_stock=round(pnl_stock, 2),
                pnl_spy_hedge=round(pnl_spy, 2),
                pnl_net=round(pnl_net, 2),
                return_pct=round((pnl_net / notional) * 100.0, 2),
                hit_disaster_stop=hit_stop,
            ))

        n_trades = len(trades)
        pnls = [t.pnl_net for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        profit_factor = (sum(wins) / sum(losses)) if sum(losses) > 0 else 999.0
        avg_ret_pct = (sum(t.return_pct for t in trades) / n_trades) if n_trades > 0 else 0.0

        return {
            "trades_count": n_trades,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "avg_return_per_event_pct": round(avg_ret_pct, 2),
            "total_net_pnl": round(sum(pnls), 2),
            "trades": trades,
        }
