"""Configuration system for Laya & JEV non-autoregressive gates and multi-asset risk policies."""

from __future__ import annotations
import os
from enum import Enum
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field, ConfigDict


class RouterType(str, Enum):
    """Decision router mode."""
    LAYA = "laya"       # Fast non-autoregressive Laya classifier
    JEV = "jev"         # Non-autoregressive Joint Energy / Vector verifier bot
    HYBRID = "hybrid"   # Primary Laya with automatic JEV fallback on low confidence


class StockRiskConfig(BaseModel):
    """Stock / Equity risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_position_concentration: float = Field(default=0.15, description="Max portfolio weight in single stock")
    max_beta: float = Field(default=2.5, description="Max allowable stock beta")
    min_market_cap_usd: float = Field(default=100_000_000.0, description="Minimum allowable market cap")


class BondRiskConfig(BaseModel):
    """Fixed Income risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_duration_years: float = Field(default=10.0, description="Max allowable modified duration")
    min_credit_rating: str = Field(default="BBB-", description="Minimum permissible credit rating")
    max_yield_spread_bps: float = Field(default=500.0, description="Max allowable credit spread in basis points")


class OptionRiskConfig(BaseModel):
    """Option derivatives risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_portfolio_delta: float = Field(default=0.50, description="Max absolute delta per underlying")
    max_portfolio_vega: float = Field(default=250.0, description="Max portfolio vega exposure in USD/1% vol")
    max_portfolio_gamma: float = Field(default=0.10, description="Max portfolio gamma")
    min_days_to_expiration: int = Field(default=2, description="Do not enter positions expiring within N days")
    max_implied_volatility: float = Field(default=1.20, description="Max IV (120%)")


class CommodityRiskConfig(BaseModel):
    """Commodity futures/spot risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_contango_roll_pct: float = Field(default=0.06, description="Max acceptable annualized negative roll yield")
    prohibit_physical_delivery: bool = Field(default=True, description="Reject contracts nearing first notice day")
    min_days_before_notice: int = Field(default=5, description="Days before first notice date to exit")


class ETFRiskConfig(BaseModel):
    """Exchange Traded Fund risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_tracking_error: float = Field(default=0.015, description="Max tracking error to benchmark")
    max_premium_discount_pct: float = Field(default=0.02, description="Max deviation from NAV")
    max_leverage_multiplier: float = Field(default=3.0, description="Max leverage on leveraged ETFs")


class MutualFundRiskConfig(BaseModel):
    """Mutual fund risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_expense_ratio: float = Field(default=0.015, description="Max expense ratio (1.5%)")
    min_holding_period_days: int = Field(default=30, description="Enforce minimum holding period for redemption")
    cutoff_buffer_minutes: int = Field(default=60, description="Orders must be submitted N minutes prior to cutoff")


class ForexRiskConfig(BaseModel):
    """Foreign Exchange risk boundaries."""
    model_config = ConfigDict(extra="ignore")
    max_leverage: float = Field(default=30.0, description="Max allowed account leverage")
    max_pip_risk_per_trade: float = Field(default=50.0, description="Max stop loss distance in pips")
    max_currency_concentration: float = Field(default=0.30, description="Max exposure to a single base/quote currency")


class ThresholdConfig(BaseModel):
    """Threshold settings for Laya and JEV decision gates."""
    model_config = ConfigDict(extra="ignore")
    # Gate 1: Market Regime
    regime_skip_on_choppy: bool = Field(default=True, description="Skip full analysis if market regime is choppy")
    regime_skip_on_crisis: bool = Field(default=True, description="Skip full analysis if market regime is crisis")
    volatility_macro_only: float = Field(default=0.70, description="Run only macro node if volatility > threshold")

    # Gate 2: News Risk
    news_risk_macro_only: float = Field(default=0.85, description="Run macro node only if macro impact high & signal quality > threshold")
    news_signal_quality_min: float = Field(default=0.30, description="Skip ticker for today if signal quality < threshold")

    # Gate 3: Thesis Quality
    analyst_agreement_escalate: float = Field(default=0.60, description="Escalate to human if agreement < threshold")
    thesis_conviction_min: float = Field(default=0.70, description="Minimum conviction level required")
    thesis_actionable_min: float = Field(default=0.70, description="Reduce size or skip if actionable < threshold")

    # Gate 4: Risk Compliance
    acceptable_risk_reward_min: float = Field(default=0.65, description="Minimum acceptable risk/reward score")
    violation_threshold: float = Field(default=0.50, description="Any violation score > threshold triggers REJECT")
    reduce_size_factor: float = Field(default=0.50, description="Size reduction multiplier if risk/reward is borderline")

    # Non-Autoregressive Routing: Fallback trigger
    laya_fallback_confidence: float = Field(
        default=0.65, description="If Laya confidence < threshold, fallback to JEV in hybrid mode"
    )


class PolicyConfig(BaseModel):
    """Global portfolio risk policy constraints."""
    model_config = ConfigDict(extra="ignore")
    max_loss_per_day: float = Field(default=500.0, description="Maximum daily portfolio loss limit in USD")
    max_position_concentration: float = Field(default=0.15, description="Maximum portfolio weight per single position")
    max_leverage: float = Field(default=2.0, description="Maximum overall portfolio leverage")
    require_stop_loss: bool = Field(default=True, description="Enforce stop-loss specification on all orders")


class LayaConfig(BaseModel):
    """Master configuration for Laya/JEV gates and multi-asset trading."""
    model_config = ConfigDict(extra="ignore")
    enabled: bool = Field(default=True, description="Master switch for Laya control layer")
    router_type: RouterType = Field(default=RouterType.HYBRID, description="Router: laya, jev, or hybrid")
    
    # Gate activation flags
    preflight_regime_gate: bool = Field(default=True, description="Enable Gate 1: Market Regime")
    news_risk_gate: bool = Field(default=True, description="Enable Gate 2: News Risk")
    post_analyst_quality_gate: bool = Field(default=True, description="Enable Gate 3: Thesis Quality")
    risk_compliance_gate: bool = Field(default=True, description="Enable Gate 4: Risk Compliance")

    # Sub-configurations
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)

    # Asset-specific risk bounds
    stock_risk: StockRiskConfig = Field(default_factory=StockRiskConfig)
    bond_risk: BondRiskConfig = Field(default_factory=BondRiskConfig)
    option_risk: OptionRiskConfig = Field(default_factory=OptionRiskConfig)
    commodity_risk: CommodityRiskConfig = Field(default_factory=CommodityRiskConfig)
    etf_risk: ETFRiskConfig = Field(default_factory=ETFRiskConfig)
    mutual_fund_risk: MutualFundRiskConfig = Field(default_factory=MutualFundRiskConfig)
    forex_risk: ForexRiskConfig = Field(default_factory=ForexRiskConfig)

    # Logging and metrics
    audit_log_path: str = Field(default="audit_trail.jsonl", description="Audit log file destination")
    enable_metrics: bool = Field(default=True, description="Track latency, skip rate, and cost metrics")

    @classmethod
    def from_yaml(cls, path: str) -> "LayaConfig":
        """Load configuration from a YAML file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # Flatten top-level structure if nested
        config_data = {}
        if "laya_gates" in data:
            config_data.update(data["laya_gates"])
        if "thresholds" in data:
            config_data["thresholds"] = data["thresholds"]
        if "policy" in data:
            config_data["policy"] = data["policy"]
        if "router_type" in data:
            config_data["router_type"] = data["router_type"]
        for key in ["stock_risk", "bond_risk", "option_risk", "commodity_risk", "etf_risk", "mutual_fund_risk", "forex_risk"]:
            if key in data:
                config_data[key] = data[key]
        
        # Also copy any raw root items
        for k, v in data.items():
            if k not in ["laya_gates", "thresholds", "policy"]:
                config_data[k] = v

        return cls(**config_data)

    @classmethod
    def from_env(cls) -> "LayaConfig":
        """Load configuration with environment variable overrides."""
        config = cls()
        if "LAYA_ENABLED" in os.environ:
            config.enabled = os.environ["LAYA_ENABLED"].lower() in ("true", "1", "yes")
        if "ROUTER_TYPE" in os.environ:
            config.router_type = RouterType(os.environ["ROUTER_TYPE"].lower())
        if "AUDIT_LOG_PATH" in os.environ:
            config.audit_log_path = os.environ["AUDIT_LOG_PATH"]
        return config
