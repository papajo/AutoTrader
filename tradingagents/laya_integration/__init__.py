"""Laya & JEV non-autoregressive control layer integration for TradingAgents."""

from tradingagents.laya_integration.config import (
    LayaConfig,
    RouterType,
    ThresholdConfig,
    PolicyConfig,
    StockRiskConfig,
    BondRiskConfig,
    OptionRiskConfig,
    CommodityRiskConfig,
    ETFRiskConfig,
    MutualFundRiskConfig,
    ForexRiskConfig,
)
from tradingagents.laya_integration.schemas import (
    AssetClass,
    GateResult,
    ProposedTrade,
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
    StockDetails,
    BondDetails,
    OptionDetails,
    CommodityDetails,
    ETFDetails,
    MutualFundDetails,
    ForexDetails,
)
from tradingagents.laya_integration.router import (
    BaseRouter,
    LayaRouter,
    JEVRouter,
    UnifiedNonAutoregressiveRouter,
    NonAutoregressiveRouter,
    UnifiedRouter,
)
from tradingagents.laya_integration.policy import trading_gates_policy
from tradingagents.laya_integration.gates import (
    BaseGate,
    PreflightGate,
    NewsRiskGate,
    ThesisQualityGate,
    RiskComplianceGate,
    LayaGates,
)
from tradingagents.laya_integration.hooks import (
    AuditLogger,
    MetricsCollector,
)

__all__ = [
    # Master orchestrator and gates
    "LayaGates",
    "BaseGate",
    "PreflightGate",
    "NewsRiskGate",
    "ThesisQualityGate",
    "RiskComplianceGate",
    # Config
    "LayaConfig",
    "RouterType",
    "ThresholdConfig",
    "PolicyConfig",
    "StockRiskConfig",
    "BondRiskConfig",
    "OptionRiskConfig",
    "CommodityRiskConfig",
    "ETFRiskConfig",
    "MutualFundRiskConfig",
    "ForexRiskConfig",
    # Policy
    "trading_gates_policy",
    # Non-autoregressive routers
    "BaseRouter",
    "LayaRouter",
    "JEVRouter",
    "UnifiedNonAutoregressiveRouter",
    "NonAutoregressiveRouter",
    "UnifiedRouter",
    # Schemas
    "AssetClass",
    "GateResult",
    "ProposedTrade",
    "MarketRegimeQuestions",
    "NewsRiskQuestions",
    "ThesisQualityQuestions",
    "RiskComplianceQuestions",
    "StockDetails",
    "BondDetails",
    "OptionDetails",
    "CommodityDetails",
    "ETFDetails",
    "MutualFundDetails",
    "ForexDetails",
    # Logging and Metrics
    "AuditLogger",
    "MetricsCollector",
]
