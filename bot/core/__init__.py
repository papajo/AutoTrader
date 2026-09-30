"""Core backtesting foundation implementing Prompt 0."""

from bot.core.contracts import Snapshot, Decision, ActionType
from bot.core.data import StockDataClient, BARS_PER_REGULAR_DAY_5M
from bot.core.features import (
    compute_atr,
    compute_ema,
    compute_session_vwap,
    resample_bars,
    align_higher_timeframe,
)
from bot.core.decision import (
    BaseDecider,
    RuleDecider,
    GateDecider,
    JevDecider,
)
from bot.core.engine import (
    Instrument,
    TradeRecord,
    BacktestEngine,
)
from bot.core.metrics import compute_metrics

__all__ = [
    "Snapshot",
    "Decision",
    "ActionType",
    "StockDataClient",
    "BARS_PER_REGULAR_DAY_5M",
    "compute_atr",
    "compute_ema",
    "compute_session_vwap",
    "resample_bars",
    "align_higher_timeframe",
    "BaseDecider",
    "RuleDecider",
    "GateDecider",
    "JevDecider",
    "Instrument",
    "TradeRecord",
    "BacktestEngine",
    "compute_metrics",
]
