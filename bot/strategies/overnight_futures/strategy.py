"""Prompt 4: Overnight Futures Reversal Strategy across Equity Index Futures.

Strictly follows:
- Rule 10: Futures session 18:00 to 17:00 ET with 6-hour clock forward shift.
- Rule 7: Sized as micros (MES, MNQ, M2K, MYM) against margin.
- Causal multi-index cross-confirmation (Asia 18:00-03:00, Europe 03:00-09:30, US 09:30-16:00).
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.engine import BacktestEngine, Instrument, TradeRecord


@dataclass
class FuturesSweepCandidate:
    """A liquidity sweep setup candidate."""
    symbol: str
    session_date: Any
    timestamp: datetime
    session_block: str  # 'asia', 'europe', 'us'
    side: str  # 'long' (swept low), 'short' (swept high)
    entry_price: float
    stop_price: float
    target_price: float
    prior_high: float
    prior_low: float
    prior_range: float
    other_confirmations_count: int = 0
    entry_idx: int = 0


class OvernightFuturesStrategy:
    """Overnight liquidity-sweep reversal across ES, NQ, RTY, YM continuous contracts."""

    SYMBOLS = ["MES", "MNQ", "M2K", "MYM"]

    def __init__(
        self,
        instruments: Optional[Dict[str, Instrument]] = None,
    ):
        self.instruments = instruments or {
            "MES": Instrument.mes(),
            "MNQ": Instrument.mnq(),
            "M2K": Instrument.m2k(),
            "MYM": Instrument.mym(),
            "ES": Instrument.es(),
        }

    @staticmethod
    def shift_futures_session(df: pd.DataFrame) -> pd.DataFrame:
        """Rule 10: Shift the clock forward six hours so 18:00 ET becomes the start of the session day."""
        df_shifted = df.copy()
        # Shift timestamps forward by 6 hours
        shifted_index = df.index + pd.Timedelta(hours=6)
        df_shifted["session_day"] = shifted_index.date
        return df_shifted

    @staticmethod
    def classify_session_block(timestamp: datetime) -> str:
        """Classify bar into Asia (18:00-03:00), Europe (03:00-09:30), or US (09:30-16:00)."""
        t = timestamp.time()
        if t >= time(18, 0) or t < time(3, 0):
            return "asia"
        elif time(3, 0) <= t < time(9, 30):
            return "europe"
        else:
            return "us"

    def detect_sweeps(
        self,
        symbol: str,
        df_5m: pd.DataFrame,
    ) -> List[FuturesSweepCandidate]:
        """Detect liquidity sweep triggers with 25% retracement entry and 12.5% stop."""
        df_shifted = self.shift_futures_session(df_5m)
        candidates: List[FuturesSweepCandidate] = []

        # Compute prior session range
        session_groups = df_shifted.groupby("session_day")
        session_ranges = {}
        for s_day, s_bars in session_groups:
            session_ranges[s_day] = {
                "high": s_bars["high"].max(),
                "low": s_bars["low"].min(),
                "range": s_bars["high"].max() - s_bars["low"].min(),
            }

        sorted_days = sorted(list(session_ranges.keys()))

        for d_idx in range(1, len(sorted_days)):
            curr_day = sorted_days[d_idx]
            prev_day = sorted_days[d_idx - 1]

            prior_h = session_ranges[prev_day]["high"]
            prior_l = session_ranges[prev_day]["low"]
            prior_rng = session_ranges[prev_day]["range"]

            # Skip sessions with implausibly small or large range
            if prior_rng <= 0.0 or prior_rng > (prior_h * 0.10):
                continue

            day_bars = df_shifted[df_shifted["session_day"] == curr_day]
            if len(day_bars) < 10:
                continue

            # Levels
            # Low sweep (bullish): swept low, retrace 25% of prior range from low
            long_entry = prior_l + 0.25 * prior_rng
            long_stop = prior_l + 0.125 * prior_rng
            long_target = prior_l + 0.50 * prior_rng

            # High sweep (bearish): swept high, retrace 25% of prior range from high
            short_entry = prior_h - 0.25 * prior_rng
            short_stop = prior_h - 0.125 * prior_rng
            short_target = prior_h - 0.50 * prior_rng

            attempted_long = False
            attempted_short = False
            swept_low = False
            swept_high = False

            for i in range(1, len(day_bars)):
                bar = day_bars.iloc[i]
                prev_bar = day_bars.iloc[i - 1]
                ts = bar.name

                # Check low sweep
                if bar["low"] < prior_l:
                    swept_low = True
                # Check high sweep
                if bar["high"] > prior_h:
                    swept_high = True

                # Long trigger: swept low -> closed back inside -> closed across 25% retrace
                if swept_low and not attempted_long:
                    if prev_bar["close"] < long_entry and bar["close"] >= long_entry:
                        candidates.append(FuturesSweepCandidate(
                            symbol=symbol,
                            session_date=curr_day,
                            timestamp=ts,
                            session_block=self.classify_session_block(ts),
                            side="long",
                            entry_price=bar["close"],
                            stop_price=long_stop,
                            target_price=long_target,
                            prior_high=prior_h,
                            prior_low=prior_l,
                            prior_range=prior_rng,
                            entry_idx=df_5m.index.get_loc(ts),
                        ))
                        attempted_long = True

                # Short trigger: swept high -> closed back inside -> closed across 25% retrace
                if swept_high and not attempted_short:
                    if prev_bar["close"] > short_entry and bar["close"] <= short_entry:
                        candidates.append(FuturesSweepCandidate(
                            symbol=symbol,
                            session_date=curr_day,
                            timestamp=ts,
                            session_block=self.classify_session_block(ts),
                            side="short",
                            entry_price=bar["close"],
                            stop_price=short_stop,
                            target_price=short_target,
                            prior_high=prior_h,
                            prior_low=prior_l,
                            prior_range=prior_rng,
                            entry_idx=df_5m.index.get_loc(ts),
                        ))
                        attempted_short = True

        return candidates

    def run_strategy(
        self,
        all_bars: Dict[str, pd.DataFrame],
        initial_capital: float = 10_000.0,
    ) -> Dict[str, Any]:
        """Execute the overnight reversal strategy across all index futures."""
        all_candidates: Dict[str, List[FuturesSweepCandidate]] = {}
        for sym in self.SYMBOLS:
            df = all_bars.get(sym)
            if df is not None and not df.empty:
                all_candidates[sym] = self.detect_sweeps(sym, df)

        # Cross-index confirmation counting (causal: only count if other index swept before this timestamp)
        for sym, cands in all_candidates.items():
            other_symbols = [s for s in self.SYMBOLS if s != sym]
            for cand in cands:
                confirmations = 0
                for o_sym in other_symbols:
                    o_cands = all_candidates.get(o_sym, [])
                    # Check if other symbol had already confirmed in same direction during this session
                    if any(c.session_date == cand.session_date and c.side == cand.side and c.timestamp <= cand.timestamp for c in o_cands):
                        confirmations += 1
                cand.other_confirmations_count = confirmations

        # Simulate trades for each slicing condition
        results = {}
        engine_all = BacktestEngine(initial_capital=initial_capital, instruments=self.instruments)
        engine_asia = BacktestEngine(initial_capital=initial_capital, instruments=self.instruments)
        engine_confirmed = BacktestEngine(initial_capital=initial_capital, instruments=self.instruments)

        for sym, cands in all_candidates.items():
            df = all_bars[sym]
            
            # Slices
            signals_all = [{"entry_idx": c.entry_idx, "side": c.side, "stop_price": c.stop_price, "target_price": c.target_price, "approved": True} for c in cands]
            signals_asia = [{"entry_idx": c.entry_idx, "side": c.side, "stop_price": c.stop_price, "target_price": c.target_price, "approved": c.session_block == "asia"} for c in cands]
            signals_confirmed = [{"entry_idx": c.entry_idx, "side": c.side, "stop_price": c.stop_price, "target_price": c.target_price, "approved": (c.session_block == "asia" and c.other_confirmations_count >= 1)} for c in cands]

            engine_all.run_strategy(df, sym, signals_all, arm_name="all_sessions")
            engine_asia.run_strategy(df, sym, signals_asia, arm_name="asia_only")
            engine_confirmed.run_strategy(df, sym, signals_confirmed, arm_name="asia_confirmed")

        from bot.core.metrics import compute_metrics
        return {
            "all_sessions": compute_metrics(engine_all.trades, initial_capital),
            "asia_only": compute_metrics(engine_asia.trades, initial_capital),
            "asia_confirmed": compute_metrics(engine_confirmed.trades, initial_capital),
        }
