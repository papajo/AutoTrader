"""Prompt 1: Opening Range Breakout (ORB) filtered by Jev on US Equities.

Three arms:
1. Rules: Takes every breakout conforming to the base mechanics.
2. Gated: Handwritten technical filters (the control arm per Rule 14).
3. Jev: Non-autoregressive decision model thresholded at 0.30 probability.
"""

from __future__ import annotations
import math
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.contracts import ActionType, Snapshot
from bot.core.data import StockDataClient
from bot.core.decision import GateDecider, JevDecider, RuleDecider
from bot.core.engine import BacktestEngine, Instrument
from bot.core.features import (
    align_higher_timeframe,
    compute_atr,
    compute_ema,
    resample_bars,
)
from bot.core.metrics import compute_metrics


class ORBStrategy:
    """Opening Range Breakout Strategy."""

    SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMD"]

    def __init__(
        self,
        range_minutes: int = 15,
        target_multiplier: float = 2.0,
        max_entry_time: time = time(11, 45),
        min_range_atr: float = 0.5,
        max_range_atr: float = 2.0,
    ):
        self.range_minutes = range_minutes
        self.target_multiplier = target_multiplier
        self.max_entry_time = max_entry_time
        self.min_range_atr = min_range_atr
        self.max_range_atr = max_range_atr

    def extract_candidates(
        self,
        df_5m: pd.DataFrame,
        symbol: str,
    ) -> List[Snapshot]:
        """Extract all candidate breakouts and construct Snapshot instances."""
        if df_5m.empty:
            return []

        # 1. Higher-timeframe 15m resampled series for ATR and EMAs
        df_15m = resample_bars(df_5m, "15min")
        # 14 days of 15m bars = 14 * 26 = 364 bars
        atr_15m = compute_atr(df_15m, period=364)
        ema_50_15m = compute_ema(df_15m["close"], span=50)
        ema_200_15m = compute_ema(df_15m["close"], span=200)

        # Rule 9: Align higher-timeframe features shifting forward by 15 minutes
        slow_delta = pd.Timedelta(minutes=self.range_minutes)
        atr_aligned = align_higher_timeframe(df_5m, atr_15m, slow_delta)
        ema_50_aligned = align_higher_timeframe(df_5m, ema_50_15m, slow_delta)
        ema_200_aligned = align_higher_timeframe(df_5m, ema_200_15m, slow_delta)

        # 2. Daily levels for prior day high/low and gap calculation
        df_daily = df_5m.resample("1D").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna()
        prior_high_series = df_daily["high"].shift(1).reindex(df_5m.index, method="ffill")
        prior_low_series = df_daily["low"].shift(1).reindex(df_5m.index, method="ffill")
        prior_close_series = df_daily["close"].shift(1).reindex(df_5m.index, method="ffill")

        # 3. Volume by time of day (20-day rolling average per bar time)
        df_5m_work = df_5m.copy()
        df_5m_work["bar_time"] = df_5m.index.time
        tod_vol_mean = df_5m_work.groupby("bar_time")["volume"].transform(
            lambda s: s.rolling(20, min_periods=5).mean()
        )

        candidates: List[Snapshot] = []

        # Group by session date
        for session_date, day_bars in df_5m.groupby(df_5m.index.date):
            if len(day_bars) < 6:
                continue

            # First 15m = bars from 09:30, 09:35, 09:40 (3 bars of 5m)
            opening_bars = day_bars.iloc[:3]
            orb_high = opening_bars["high"].max()
            orb_low = opening_bars["low"].min()
            orb_range = orb_high - orb_low

            # Warm-up check: Check ATR availability (Rule 8)
            current_atr = atr_aligned.loc[opening_bars.index[-1]]
            if pd.isna(current_atr) or current_atr <= 0:
                continue

            # Skip day if opening range is outside 0.5 - 2.0 ATR
            range_in_atr = orb_range / current_atr
            if range_in_atr < self.min_range_atr or range_in_atr > self.max_range_atr:
                continue

            prior_h = prior_high_series.loc[opening_bars.index[0]]
            prior_l = prior_low_series.loc[opening_bars.index[0]]
            prior_c = prior_close_series.loc[opening_bars.index[0]]

            is_inside_prior_day = (
                not pd.isna(prior_h) and not pd.isna(prior_l) and
                orb_high <= prior_h and orb_low >= prior_l
            )
            overnight_gap = (opening_bars.iloc[0]["open"] - prior_c) if not pd.isna(prior_c) else 0.0

            # Scan bars starting at 09:45 (bar index 3) up to max_entry_time (11:45)
            attempt_made = False
            upper_tests = 0
            lower_tests = 0

            for i in range(3, len(day_bars)):
                if attempt_made:
                    break

                curr_bar = day_bars.iloc[i]
                prev_bar = day_bars.iloc[i - 1]
                bar_time = curr_bar.name.time()

                if bar_time > self.max_entry_time:
                    break

                # Count touches/tests of the boundaries
                if prev_bar["high"] >= orb_high * 0.999:
                    upper_tests += 1
                if prev_bar["low"] <= orb_low * 1.001:
                    lower_tests += 1

                # Strict confirmation rule:
                # PREVIOUS bar closed inside range AND current bar closed strictly outside
                long_trigger = (prev_bar["close"] <= orb_high) and (curr_bar["close"] > orb_high)
                short_trigger = (prev_bar["close"] >= orb_low) and (curr_bar["close"] < orb_low)

                if not (long_trigger or short_trigger):
                    continue

                action: ActionType = "enter_long" if long_trigger else "enter_short"
                close_price = curr_bar["close"]

                # Candidate metrics
                bar_range = curr_bar["high"] - curr_bar["low"]
                body_pct = abs(curr_bar["close"] - curr_bar["open"]) / max(0.001, bar_range)
                upper_wick = (curr_bar["high"] - max(curr_bar["open"], curr_bar["close"])) / max(0.001, bar_range)
                lower_wick = (min(curr_bar["open"], curr_bar["close"]) - curr_bar["low"]) / max(0.001, bar_range)

                expected_tod_vol = tod_vol_mean.loc[curr_bar.name]
                vol_ratio = (curr_bar["volume"] / expected_tod_vol) if (not pd.isna(expected_tod_vol) and expected_tod_vol > 0) else 1.0

                ema_50 = ema_50_aligned.loc[curr_bar.name]
                ema_200 = ema_200_aligned.loc[curr_bar.name]
                dist_ema50_atr = ((close_price - ema_50) / current_atr) if not pd.isna(ema_50) else 0.0
                dist_ema200_atr = ((close_price - ema_200) / current_atr) if not pd.isna(ema_200) else 0.0

                dist_past_edge_atr = ((close_price - orb_high) if long_trigger else (orb_low - close_price)) / current_atr
                next_round = math.ceil(close_price) if long_trigger else math.floor(close_price)
                dist_to_round_atr = abs(next_round - close_price) / current_atr

                # Numeric features for GateDecider
                features = {
                    "orb_range_atr": range_in_atr,
                    "dist_past_edge_atr": dist_past_edge_atr,
                    "body_pct": body_pct,
                    "wick_pct": upper_wick if long_trigger else lower_wick,
                    "vol_ratio_tod": vol_ratio,
                    "dist_ema50_atr": dist_ema50_atr,
                    "dist_ema200_atr": dist_ema200_atr,
                    "edge_tests": upper_tests if long_trigger else lower_tests,
                    "is_inside_prior_day": 1.0 if is_inside_prior_day else 0.0,
                    "overnight_gap_atr": overnight_gap / current_atr,
                    "dist_to_round_atr": dist_to_round_atr,
                }

                # Plain-English context lines for JevDecider (Rule 8: no uninitialized 0.0 indicators)
                trend_desc = "above 50 & 200 EMA (bullish alignment)" if dist_ema50_atr > 0 and dist_ema200_atr > 0 else (
                    "below 50 & 200 EMA (bearish alignment)" if dist_ema50_atr < 0 and dist_ema200_atr < 0 else "mixed EMA alignment"
                )
                context = [
                    f"Opening range is {range_in_atr:.2f} ATR wide.",
                    f"Breakout bar closed {dist_past_edge_atr:.2f} ATR past the range edge with {body_pct:.1%} body.",
                    f"Volume is {vol_ratio:.2f}x the 20-day average for this time of day.",
                    f"Higher timeframe trend: {trend_desc}; price is {abs(dist_ema50_atr):.2f} ATR from 50 EMA.",
                    f"The breakout edge was tested {upper_tests if long_trigger else lower_tests} times prior to breakout.",
                    f"Overnight gap was {overnight_gap:.2f} ({overnight_gap / current_atr:+.2f} ATR).",
                    f"Range sits {'inside' if is_inside_prior_day else 'outside'} yesterday's range.",
                    f"Distance to next psychological round number (${next_round}) is {dist_to_round_atr:.2f} ATR.",
                ]

                # Stop and target levels
                stop_price = orb_low if long_trigger else orb_high
                stop_distance = abs(close_price - stop_price)
                target_price = (close_price + stop_distance * self.target_multiplier) if long_trigger else (close_price - stop_distance * self.target_multiplier)

                snap = Snapshot(
                    symbol=symbol,
                    timestamp=curr_bar.name,
                    price=close_price,
                    action=action,
                    features=features,
                    context=context,
                    metadata={
                        "entry_idx": df_5m.index.get_loc(curr_bar.name),
                        "stop_price": stop_price,
                        "target_price": target_price,
                        "side": "long" if long_trigger else "short",
                    },
                )
                candidates.append(snap)
                attempt_made = True  # Max 1 attempt per symbol per session

        return candidates

    @staticmethod
    def get_gated_arm() -> GateDecider:
        """Hand-written filters arm (the control arm):

        Vetoes:
        1. Counter-trend breakouts (against 50 EMA)
        2. Weak-bodied candles (< 40% body)
        3. Breakouts that already ran (> 0.7 ATR past edge)
        4. Over-tested edges (> 4 tests)
        """
        gated = GateDecider()
        gated.add_veto(lambda s: (s.action == "enter_long" and s.features.get("dist_ema50_atr", 0.0) < -0.1, "Counter-trend long below 50 EMA"))
        gated.add_veto(lambda s: (s.action == "enter_short" and s.features.get("dist_ema50_atr", 0.0) > 0.1, "Counter-trend short above 50 EMA"))
        gated.add_veto(lambda s: (s.features.get("body_pct", 1.0) < 0.40, "Weak candle body (< 40%)"))
        gated.add_veto(lambda s: (s.features.get("dist_past_edge_atr", 0.0) > 0.70, "Breakout already ran (> 0.70 ATR)"))
        gated.add_veto(lambda s: (s.features.get("edge_tests", 0) > 4, "Over-tested edge (> 4 tests)"))
        return gated

    def run_all_three_arms(
        self,
        symbol: str,
        start_date: str = "2023-01-01",
        end_date: str = "2026-09-01",
        client: Optional[StockDataClient] = None,
    ) -> Dict[str, Any]:
        """Run all three arms (Rules, Gated, Jev @ 0.30) and return comparison."""
        client = client or StockDataClient()
        df = client.fetch_bars(symbol, start_date, end_date)
        candidates = self.extract_candidates(df, symbol)

        rule_decider = RuleDecider()
        gated_decider = self.get_gated_arm()
        jev_decider = JevDecider(probability_threshold=0.30)

        results = {}
        for arm_name, decider in [("rules", rule_decider), ("gated", gated_decider), ("jev", jev_decider)]:
            engine = BacktestEngine(initial_capital=10000.0, risk_per_trade_pct=0.01)
            signals = []
            for cand in candidates:
                decision = decider.decide(cand)
                signals.append({
                    "entry_idx": cand.metadata["entry_idx"],
                    "side": cand.metadata["side"],
                    "stop_price": cand.metadata["stop_price"],
                    "target_price": cand.metadata["target_price"],
                    "approved": decision.approved,
                })
            trades = engine.run_strategy(df, symbol, signals, arm_name=arm_name)
            metrics = compute_metrics(trades, initial_capital=10000.0)
            results[arm_name] = {
                "metrics": metrics,
                "trades": trades,
                "candidates_count": len(candidates),
                "approved_count": sum(1 for s in signals if s["approved"]),
            }

        return results
