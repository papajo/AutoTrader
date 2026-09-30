"""TradingAgents: Multi-Agent Trading Framework with Non-Autoregressive Laya/JEV Control Layer.

Applicable across Stocks, Bonds, Options, Commodities, ETFs, Mutual Funds, and Forex.
"""

from tradingagents.laya_integration import (
    LayaGates,
    LayaConfig,
    trading_gates_policy,
    NonAutoregressiveRouter,
    LayaRouter,
    JEVRouter,
    UnifiedRouter,
)

__version__ = "0.6.0"
__all__ = [
    "LayaGates",
    "LayaConfig",
    "trading_gates_policy",
    "NonAutoregressiveRouter",
    "LayaRouter",
    "JEVRouter",
    "UnifiedRouter",
]
