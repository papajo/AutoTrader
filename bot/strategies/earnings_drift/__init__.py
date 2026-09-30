"""Post-Earnings Announcement Drift (PEAD) strategy implementing Prompt 3."""

from bot.strategies.earnings_drift.parser import SEC8KParser, EarningsEvent
from bot.strategies.earnings_drift.strategy import PostEarningsDriftStrategy, HedgedPEADTrade

__all__ = [
    "SEC8KParser",
    "EarningsEvent",
    "PostEarningsDriftStrategy",
    "HedgedPEADTrade",
]
