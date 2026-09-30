"""Prompt 6: Lunar Phase & Gann Geometry Strategy with Placebo Testing.

Tests:
1. Placebo arm on shifted calendars.
2. 30-shift scan ranking the true calendar vs random day shifts.
3. Post-publication decay demonstration.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.contracts import ActionType, Snapshot
from bot.core.decision import JevDecider, RuleDecider
from bot.core.engine import BacktestEngine
from bot.core.features import compute_atr
from bot.core.metrics import compute_metrics
from bot.strategies.lunar_gann.ephemeris import LunarEphemeris


class LunarPhaseStrategy:
    """Lunar phase anomaly strategy on daily bars."""

    def __init__(
        self,
        holding_bars: int = 10,
        stop_atr_mult: float = 1.5,
        target_atr_mult: float = 3.0,
    ):
        self.holding_bars = holding_bars
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult

    def generate_candidates(
        self,
        df_daily: pd.DataFrame,
        symbol: str,
        calendar_shift_days: int = 0,
    ) -> List[Snapshot]:
        """Generate trade candidates based on lunar cycle (or shifted placebo calendar)."""
        if df_daily.empty or len(df_daily) < 30:
            return []

        df_work = df_daily.copy()
        atr_series = compute_atr(df_work, period=14)
        candidates: List[Snapshot] = []

        for i in range(15, len(df_work)):
            bar = df_work.iloc[i]
            ts = bar.name
            
            # Apply placebo calendar shift (Rule 19)
            shifted_ts = ts + timedelta(days=calendar_shift_days) if calendar_shift_days != 0 else ts
            dt_utc = shifted_ts.to_pydatetime()

            is_new = LunarEphemeris.is_new_moon(dt_utc)
            is_full = LunarEphemeris.is_full_moon(dt_utc)

            if not (is_new or is_full):
                continue

            current_atr = atr_series.iloc[i]
            if pd.isna(current_atr) or current_atr <= 0:
                continue

            # Classical rule: Long on New Moon, Short on Full Moon
            action: ActionType = "enter_long" if is_new else "enter_short"
            side = "long" if is_new else "short"
            close_p = bar["close"]

            if side == "long":
                stop_p = close_p - (current_atr * self.stop_atr_mult)
                target_p = close_p + (current_atr * self.target_atr_mult)
            else:
                stop_p = close_p + (current_atr * self.stop_atr_mult)
                target_p = close_p - (current_atr * self.target_atr_mult)

            snap = Snapshot(
                symbol=symbol,
                timestamp=ts,
                price=close_p,
                action=action,
                features={
                    "is_new_moon": 1.0 if is_new else 0.0,
                    "is_full_moon": 1.0 if is_full else 0.0,
                    "calendar_shift": float(calendar_shift_days),
                    "atr": current_atr,
                },
                context=[
                    f"Date: {ts.strftime('%Y-%m-%d')}",
                    f"Moon Phase: {'New Moon' if is_new else 'Full Moon'}",
                    f"Calendar Shift: {calendar_shift_days} days",
                    f"Price: ${close_p:.2f} | 14-day ATR: ${current_atr:.2f}",
                ],
                metadata={
                    "entry_idx": i,
                    "side": side,
                    "stop_price": stop_p,
                    "target_price": target_p,
                    "max_bars": self.holding_bars,
                },
            )
            candidates.append(snap)

        return candidates

    def run_shift_scan(
        self,
        df_daily: pd.DataFrame,
        symbol: str,
        n_shifts: int = 30,
        initial_capital: float = 10_000.0,
    ) -> Dict[str, Any]:
        """Prompt 6 test 2: Rank the true calendar (shift=0) against 30 shifted placebo calendars."""
        shift_results = []

        for shift in range(n_shifts):
            cands = self.generate_candidates(df_daily, symbol, calendar_shift_days=shift)
            engine = BacktestEngine(initial_capital=initial_capital)
            signals = [{
                "entry_idx": c.metadata["entry_idx"],
                "side": c.metadata["side"],
                "stop_price": c.metadata["stop_price"],
                "target_price": c.metadata["target_price"],
                "max_bars": self.holding_bars,
                "approved": True,
            } for c in cands]

            engine.run_strategy(df_daily, symbol, signals, arm_name=f"shift_{shift}")
            metrics = compute_metrics(engine.trades, initial_capital)
            shift_results.append({
                "shift_days": shift,
                "trades": metrics["trades"],
                "profit_factor": metrics["profit_factor"],
                "sum_of_r": metrics["sum_of_r"],
                "win_rate": metrics["win_rate"],
            })

        # Rank by profit factor
        sorted_by_pf = sorted(shift_results, key=lambda x: x["profit_factor"], reverse=True)
        true_calendar_rank = next(i + 1 for i, r in enumerate(sorted_by_pf) if r["shift_days"] == 0)

        return {
            "symbol": symbol,
            "true_calendar_rank": true_calendar_rank,
            "total_shifts_tested": n_shifts,
            "true_calendar_metrics": shift_results[0],
            "all_shifts": shift_results,
        }
