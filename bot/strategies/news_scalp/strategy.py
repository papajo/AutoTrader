"""Prompt 5: News Scalp Strategy on Earnings Gaps.

Compares reading headlines vs reading the tape on the first 5-minute bar of earnings releases.
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.contracts import ActionType, Snapshot
from bot.core.decision import GateDecider, JevDecider, RuleDecider
from bot.core.engine import BacktestEngine, Instrument
from bot.core.metrics import compute_metrics
from bot.strategies.earnings_drift.parser import EarningsEvent


@dataclass
class NewsHeadline:
    """A news headline article with timestamp."""
    headline: str
    published_at: datetime
    source: str = "alpaca_news"


class NewsScalpStrategy:
    """Earnings-gap scalp strategy comparing tape metrics vs LLM headline reading."""

    def __init__(
        self,
        target_r_multiplier: float = 1.5,
    ):
        self.target_r_multiplier = target_r_multiplier

    @staticmethod
    def extract_regex_sentiment(headlines: List[str]) -> float:
        """Handwritten regex keyword sentiment: +1 for beats/raises, -1 for misses/cuts."""
        positive_keywords = [r"\bbeats?\b", r"\braises?\b", r"\bsurpasses?\b", r"\boutperforms?\b", r"\bhigher\b"]
        negative_keywords = [r"\bmisses?\b", r"\bcuts?\b", r"\blowers?\b", r"\bfalls short\b", r"\bdisappoints?\b"]

        score = 0.0
        for text in headlines:
            text_lower = text.lower()
            for pat in positive_keywords:
                if re.search(pat, text_lower):
                    score += 1.0
            for pat in negative_keywords:
                if re.search(pat, text_lower):
                    score -= 1.0

        return np.clip(score, -5.0, 5.0)

    def extract_scalp_candidates(
        self,
        events: List[EarningsEvent],
        price_data: Dict[str, pd.DataFrame],
        headlines_data: Optional[Dict[str, List[NewsHeadline]]] = None,
    ) -> List[Snapshot]:
        """Extract trade snapshots at the close of the first 5m bar of earnings sessions."""
        candidates: List[Snapshot] = []
        headlines_data = headlines_data or {}

        for ev in events:
            df = price_data.get(ev.ticker)
            if df is None or df.empty:
                continue

            session_bars = df.loc[df.index.date == ev.first_tradable_date]
            prior_bars = df.loc[df.index.date < ev.first_tradable_date]

            if len(session_bars) < 2 or prior_bars.empty:
                continue

            prior_close = prior_bars.iloc[-1]["close"]
            first_bar = session_bars.iloc[0]  # 09:30 - 09:35 bar
            bar_close = first_bar["close"]
            gap_pct = (first_bar["open"] - prior_close) / prior_close

            # Skip flat opens (< 0.5% gap)
            if abs(gap_pct) < 0.005:
                continue

            direction = "long" if gap_pct > 0 else "short"
            action: ActionType = "enter_long" if direction == "long" else "enter_short"

            # Stop beyond opening drive's extreme (Prompt 5 rule)
            if direction == "long":
                stop_price = first_bar["low"]
                stop_distance = max(0.10, bar_close - stop_price)
                target_price = bar_close + (stop_distance * self.target_r_multiplier)
            else:
                stop_price = first_bar["high"]
                stop_distance = max(0.10, stop_price - bar_close)
                target_price = bar_close - (stop_distance * self.target_r_multiplier)

            # Headlines between filing and entry
            hl_list = headlines_data.get(ev.ticker, [
                NewsHeadline(f"{ev.ticker} reports quarterly results.", ev.filing_datetime)
            ])
            hl_texts = [h.headline for h in hl_list]
            regex_sent = self.extract_regex_sentiment(hl_texts)

            features = {
                "gap_pct": gap_pct,
                "first_bar_volume": float(first_bar["volume"]),
                "regex_sentiment": regex_sent,
                "stop_distance": stop_distance,
            }

            context = [
                f"Stock opened with {gap_pct:+.2%} earnings gap.",
                f"First 5m bar volume was {first_bar['volume']:,} shares.",
                f"Headlines: {' | '.join(hl_texts[:3])}",
                f"Keyword sentiment score: {regex_sent:+.1f}",
            ]

            snap = Snapshot(
                symbol=ev.ticker,
                timestamp=first_bar.name,
                price=bar_close,
                action=action,
                features=features,
                context=context,
                metadata={
                    "entry_idx": df.index.get_loc(first_bar.name),
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "side": direction,
                },
            )
            candidates.append(snap)

        return candidates

    def run_strategy(
        self,
        candidates: List[Snapshot],
        price_data: Dict[str, pd.DataFrame],
        initial_capital: float = 10_000.0,
    ) -> Dict[str, Any]:
        """Execute the 3 arms on earnings scalp candidates."""
        rule_decider = RuleDecider()
        
        # Gated arm: requires regex keyword sentiment to agree with gap direction
        gated_decider = GateDecider()
        gated_decider.add_veto(lambda s: (s.action == "enter_long" and s.features.get("regex_sentiment", 0.0) < 0, "Negative headlines on gap up"))
        gated_decider.add_veto(lambda s: (s.action == "enter_short" and s.features.get("regex_sentiment", 0.0) > 0, "Positive headlines on gap down"))

        # Jev arm
        jev_decider = JevDecider(probability_threshold=0.55)

        results = {}
        for arm_name, decider in [("rules", rule_decider), ("gated", gated_decider), ("jev", jev_decider)]:
            engine = BacktestEngine(initial_capital=initial_capital)
            for cand in candidates:
                dec = decider.decide(cand)
                df = price_data.get(cand.symbol)
                if df is None:
                    continue
                signals = [{
                    "entry_idx": cand.metadata["entry_idx"],
                    "side": cand.metadata["side"],
                    "stop_price": cand.metadata["stop_price"],
                    "target_price": cand.metadata["target_price"],
                    "approved": dec.approved,
                }]
                engine.run_strategy(df, cand.symbol, signals, arm_name=arm_name)

            results[arm_name] = compute_metrics(engine.trades, initial_capital)

        return results
