"""Pydantic v2 schemas for Laya & JEV non-autoregressive gates and multi-asset trading."""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Literal, Optional, Union, Any
from pydantic import BaseModel, Field, ConfigDict


class AssetClass(str, Enum):
    """Supported asset classes."""
    STOCK = "stock"
    BOND = "bond"
    OPTION = "option"
    COMMODITY = "commodity"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    FOREX = "forex"
    CRYPTO = "crypto"


# ---------------------------------------------------------------------------
# Multi-Asset Context Specifications
# ---------------------------------------------------------------------------

class StockDetails(BaseModel):
    """Context details for equity securities."""
    model_config = ConfigDict(extra="ignore")
    market_cap: Optional[float] = Field(default=None, description="Market cap in USD")
    beta: float = Field(default=1.0, description="Stock beta relative to market")
    sector: Optional[str] = Field(default=None, description="Sector/industry")
    pe_ratio: Optional[float] = Field(default=None, description="P/E ratio")
    shares_float: Optional[float] = Field(default=None, description="Free float shares")


class BondDetails(BaseModel):
    """Context details for fixed income securities."""
    model_config = ConfigDict(extra="ignore")
    yield_to_maturity: float = Field(..., description="Annualized yield to maturity (e.g. 0.045 for 4.5%)")
    duration: float = Field(..., description="Macaulay/Modified duration in years")
    convexity: float = Field(default=0.0, description="Bond convexity")
    credit_rating: str = Field(default="AAA", description="Credit rating (e.g. AAA, AA, BBB, BB, C)")
    coupon_rate: float = Field(default=0.0, description="Annual coupon rate")
    maturity_date: Optional[str] = Field(default=None, description="Maturity date YYYY-MM-DD")


class OptionDetails(BaseModel):
    """Context details for option contracts."""
    model_config = ConfigDict(extra="ignore")
    underlying_symbol: str = Field(..., description="Ticker of underlying asset")
    option_type: Literal["call", "put"] = Field(..., description="Option type")
    strike_price: float = Field(..., description="Strike price")
    expiration_days: int = Field(..., description="Days until expiration")
    implied_volatility: float = Field(..., description="Implied volatility (e.g. 0.28 for 28%)")
    delta: float = Field(..., description="Option Delta (-1.0 to 1.0)")
    gamma: float = Field(default=0.0, description="Option Gamma")
    vega: float = Field(default=0.0, description="Option Vega (change per 1% vol)")
    theta: float = Field(default=0.0, description="Option Theta (daily time decay)")


class CommodityDetails(BaseModel):
    """Context details for commodity contracts."""
    model_config = ConfigDict(extra="ignore")
    commodity_type: Literal["energy", "metals", "agriculture", "livestock", "other"] = Field(
        default="metals", description="Commodity sector"
    )
    contract_month: Optional[str] = Field(default=None, description="Contract month code (e.g. CLZ26)")
    curve_state: Literal["contango", "backwardation", "flat"] = Field(
        default="flat", description="Futures forward curve structure"
    )
    storage_rate: float = Field(default=0.0, description="Annualized carrying/storage cost")
    delivery_settlement: Literal["physical", "financial"] = Field(default="financial")


class ETFDetails(BaseModel):
    """Context details for Exchange Traded Funds."""
    model_config = ConfigDict(extra="ignore")
    benchmark_index: str = Field(..., description="Underlying index tracked")
    expense_ratio: float = Field(default=0.001, description="Annual expense ratio")
    nav_premium_discount: float = Field(default=0.0, description="Percentage premium (+) or discount (-) to NAV")
    leverage_factor: float = Field(default=1.0, description="Leverage multiplier (e.g. 1.0, 2.0, -3.0)")
    tracking_error: float = Field(default=0.002, description="Annual tracking error std dev")


class MutualFundDetails(BaseModel):
    """Context details for mutual funds."""
    model_config = ConfigDict(extra="ignore")
    nav: float = Field(..., description="Net Asset Value per share")
    expense_ratio: float = Field(default=0.005, description="Annual expense ratio")
    redemption_cutoff_time: str = Field(default="16:00 EST", description="Cut-off time for daily orders")
    min_holding_days: int = Field(default=30, description="Early redemption fee cutoff in days")
    turnover_ratio: float = Field(default=0.20, description="Portfolio annual turnover")


class ForexDetails(BaseModel):
    """Context details for Foreign Exchange pairs."""
    model_config = ConfigDict(extra="ignore")
    base_currency: str = Field(..., description="Base currency (e.g. EUR)")
    quote_currency: str = Field(..., description="Quote currency (e.g. USD)")
    lot_size: float = Field(default=100000.0, description="Standard lot size (e.g. 100,000)")
    pip_value: float = Field(default=10.0, description="USD value per pip per standard lot")
    spread_pips: float = Field(default=1.2, description="Current bid/ask spread in pips")
    leverage: float = Field(default=30.0, description="Account leverage for pair")
    interest_rate_differential: float = Field(
        default=0.0, description="Base rate minus quote rate (annualized carry)"
    )


AssetDetails = Union[
    StockDetails,
    BondDetails,
    OptionDetails,
    CommodityDetails,
    ETFDetails,
    MutualFundDetails,
    ForexDetails,
    Dict[str, Any],
]


# ---------------------------------------------------------------------------
# Laya Question Schemas (Reusable Pydantic v2 Models)
# ---------------------------------------------------------------------------

class MarketRegimeQuestions(BaseModel):
    """Gate 1 Question Schema: Market Regime Classifier."""
    model_config = ConfigDict(extra="ignore")
    market_trend: Literal["uptrend", "downtrend", "sideways"] = Field(
        ..., description="Dominant price trend direction"
    )
    volatility_level: float = Field(
        ..., ge=0.0, le=1.0, description="Calibrated volatility score (0.0 low to 1.0 crisis)"
    )
    market_regime: Literal["breakout", "mean_reversion", "choppy", "crisis", "bullish", "bearish"] = Field(
        ..., description="Identified macroeconomic/technical market regime"
    )


class NewsRiskQuestions(BaseModel):
    """Gate 2 Question Schema: News and Macro Risk Classifier."""
    model_config = ConfigDict(extra="ignore")
    event_type: Literal["earnings", "macro", "M&A", "guidance", "normal", "central_bank", "geopolitical"] = Field(
        default="normal", description="Dominant news event type"
    )
    macro_impact: Literal["low", "medium", "high"] = Field(
        default="low", description="Expected macroeconomic market impact"
    )
    signal_quality: float = Field(
        ..., ge=0.0, le=1.0, description="Noul metric: Is this actionable signal (1.0) or noise (0.0)?"
    )


class ThesisQualityQuestions(BaseModel):
    """Gate 3 Question Schema: Thesis Quality Scorer."""
    model_config = ConfigDict(extra="ignore")
    analyst_agreement: float = Field(
        ..., ge=0.0, le=1.0, description="Degree of directional consensus among analysts (0 to 1)"
    )
    conviction_level: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence level across analyst models (0 to 1)"
    )
    thesis_actionable: float = Field(
        ..., ge=0.0, le=1.0, description="Tradeability and risk/reward actionability (0 to 1)"
    )
    disagreement_severity: Literal["minor", "moderate", "severe"] = Field(
        default="minor", description="Severity of internal debate disagreements"
    )


class RiskComplianceQuestions(BaseModel):
    """Gate 4 Question Schema: Risk Compliance Gate."""
    model_config = ConfigDict(extra="ignore")
    violates_position_limit: float = Field(
        ..., ge=0.0, le=1.0, description="Probability or severity of exceeding position limits (>0.5 violation)"
    )
    violates_max_loss: float = Field(
        ..., ge=0.0, le=1.0, description="Probability of breaching daily/cumulative max loss (>0.5 violation)"
    )
    violates_concentration: float = Field(
        ..., ge=0.0, le=1.0, description="Probability of exceeding single-name concentration (>0.5 violation)"
    )
    acceptable_risk_reward: float = Field(
        ..., ge=0.0, le=1.0, description="Quality of expected return to downside risk profile"
    )
    violates_asset_specific_limit: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Asset specific violation (Greeks, duration, pips, etc.)"
    )


# ---------------------------------------------------------------------------
# Order Proposals and Gate Results
# ---------------------------------------------------------------------------

class ProposedTrade(BaseModel):
    """Order proposal drafted by Trader Agent."""
    model_config = ConfigDict(extra="ignore")
    symbol: str
    asset_class: AssetClass = AssetClass.STOCK
    side: Literal["buy", "sell", "hold"] = "buy"
    quantity: float
    price: float
    estimated_value: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    details: Optional[AssetDetails] = None
    rationale: str = ""


class GateResult(BaseModel):
    """Result of a Laya or JEV gate execution."""
    model_config = ConfigDict(extra="ignore")
    gate_name: str
    decision: Literal["proceed", "skip", "hedge", "escalate", "reject", "reduce"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    laya_answers: Dict[str, Any] = Field(default_factory=dict)
    execution_action: Optional[str] = None
    latency_ms: float = 0.0
    router_used: str = "laya"
    asset_class: AssetClass = AssetClass.STOCK
    timestamp: Optional[str] = None
