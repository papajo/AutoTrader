"""The 6 AI Trading Strategies implementing Prompts 1 through 6."""

from bot.strategies.orb import ORBStrategy
from bot.strategies.insider import InsiderTradingStrategy, SECForm4Parser
from bot.strategies.earnings_drift import PostEarningsDriftStrategy, SEC8KParser
from bot.strategies.overnight_futures import OvernightFuturesStrategy
from bot.strategies.news_scalp import NewsScalpStrategy
from bot.strategies.lunar_gann import LunarPhaseStrategy, LunarEphemeris

__all__ = [
    "ORBStrategy",
    "InsiderTradingStrategy",
    "SECForm4Parser",
    "PostEarningsDriftStrategy",
    "SEC8KParser",
    "OvernightFuturesStrategy",
    "NewsScalpStrategy",
    "LunarPhaseStrategy",
    "LunarEphemeris",
]
