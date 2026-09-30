"""Unit tests for Pydantic v2 schemas and multi-asset specifications."""

import pytest
from pydantic import ValidationError
from tradingagents.laya_integration.schemas import (
    AssetClass,
    StockDetails,
    BondDetails,
    OptionDetails,
    CommodityDetails,
    ETFDetails,
    MutualFundDetails,
    ForexDetails,
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
    GateResult,
    ProposedTrade,
)


def test_asset_class_enum():
    assert AssetClass.STOCK.value == "stock"
    assert AssetClass.BOND.value == "bond"
    assert AssetClass.OPTION.value == "option"
    assert AssetClass.COMMODITY.value == "commodity"
    assert AssetClass.ETF.value == "etf"
    assert AssetClass.MUTUAL_FUND.value == "mutual_fund"
    assert AssetClass.FOREX.value == "forex"


def test_multi_asset_details_validation():
    # Stock
    stock = StockDetails(market_cap=1e11, beta=1.2, sector="Tech", pe_ratio=25.0)
    assert stock.beta == 1.2

    # Bond
    bond = BondDetails(
        yield_to_maturity=0.045,
        duration=6.5,
        convexity=0.45,
        credit_rating="AA",
        coupon_rate=0.04,
    )
    assert bond.duration == 6.5
    assert bond.credit_rating == "AA"

    # Option
    option = OptionDetails(
        underlying_symbol="AAPL",
        option_type="call",
        strike_price=180.0,
        expiration_days=30,
        implied_volatility=0.25,
        delta=0.52,
        gamma=0.04,
        vega=22.0,
    )
    assert option.option_type == "call"
    assert option.delta == 0.52

    # Commodity
    commodity = CommodityDetails(
        commodity_type="energy",
        contract_month="CLZ26",
        curve_state="contango",
        storage_rate=0.04,
    )
    assert commodity.curve_state == "contango"

    # ETF
    etf = ETFDetails(
        benchmark_index="S&P 500",
        expense_ratio=0.0003,
        leverage_factor=1.0,
        tracking_error=0.001,
    )
    assert etf.tracking_error == 0.001

    # Mutual Fund
    mf = MutualFundDetails(nav=125.40, expense_ratio=0.005, min_holding_days=30)
    assert mf.nav == 125.40

    # Forex
    fx = ForexDetails(
        base_currency="GBP",
        quote_currency="USD",
        lot_size=100000.0,
        pip_value=10.0,
        spread_pips=1.5,
        leverage=30.0,
    )
    assert fx.base_currency == "GBP"


def test_laya_question_schemas():
    # Gate 1
    g1 = MarketRegimeQuestions(
        market_trend="uptrend",
        volatility_level=0.35,
        market_regime="bullish",
    )
    assert g1.market_regime == "bullish"

    # Gate 2
    g2 = NewsRiskQuestions(
        event_type="macro",
        macro_impact="high",
        signal_quality=0.88,
    )
    assert g2.macro_impact == "high"

    # Gate 3
    g3 = ThesisQualityQuestions(
        analyst_agreement=0.85,
        conviction_level=0.80,
        thesis_actionable=0.90,
        disagreement_severity="minor",
    )
    assert g3.analyst_agreement == 0.85

    # Gate 4
    g4 = RiskComplianceQuestions(
        violates_position_limit=0.1,
        violates_max_loss=0.0,
        violates_concentration=0.2,
        acceptable_risk_reward=0.85,
    )
    assert g4.acceptable_risk_reward == 0.85


def test_schema_validation_bounds():
    # Volatility out of 0.0-1.0 range
    with pytest.raises(ValidationError):
        MarketRegimeQuestions(
            market_trend="uptrend",
            volatility_level=1.5,
            market_regime="bullish",
        )

    # Invalid choice
    with pytest.raises(ValidationError):
        MarketRegimeQuestions(
            market_trend="diagonal",  # Invalid
            volatility_level=0.5,
            market_regime="bullish",
        )
