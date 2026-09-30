"""Unit tests for stateless policy engine and multi-asset risk invariants."""

import pytest
from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.policy import trading_gates_policy
from tradingagents.laya_integration.schemas import (
    AssetClass,
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
)


@pytest.fixture
def config():
    return LayaConfig()


def test_gate1_regime_policy(config):
    # Crisis -> skip
    q_crisis = MarketRegimeQuestions(market_trend="downtrend", volatility_level=0.85, market_regime="crisis")
    res = trading_gates_policy(q_crisis, config)
    assert res["decision"] == "skip"
    assert res["execution_action"] == "flat_or_hedge"

    # Choppy -> skip
    q_choppy = MarketRegimeQuestions(market_trend="sideways", volatility_level=0.10, market_regime="choppy")
    res = trading_gates_policy(q_choppy, config)
    assert res["decision"] == "skip"
    assert res["execution_action"] == "hold"

    # High Volatility -> macro only
    q_vol = MarketRegimeQuestions(market_trend="uptrend", volatility_level=0.75, market_regime="bullish")
    res = trading_gates_policy(q_vol, config)
    assert res["decision"] == "proceed"
    assert res["execution_action"] == "run_macro_only"

    # Normal Bullish -> proceed
    q_normal = MarketRegimeQuestions(market_trend="uptrend", volatility_level=0.25, market_regime="bullish")
    res = trading_gates_policy(q_normal, config)
    assert res["decision"] == "proceed"
    assert res["execution_action"] == "continue_to_analysts"


def test_gate2_news_risk_policy(config):
    # Low signal quality -> skip
    q_noise = NewsRiskQuestions(event_type="normal", macro_impact="low", signal_quality=0.20)
    res = trading_gates_policy(q_noise, config)
    assert res["decision"] == "skip"
    assert res["execution_action"] == "skip_ticker_today"

    # High macro impact -> run macro only
    q_macro = NewsRiskQuestions(event_type="central_bank", macro_impact="high", signal_quality=0.90)
    res = trading_gates_policy(q_macro, config)
    assert res["decision"] == "proceed"
    assert res["execution_action"] == "run_macro_only"


def test_gate3_thesis_quality_policy(config):
    # Low agreement -> escalate
    q_split = ThesisQualityQuestions(
        analyst_agreement=0.45,
        conviction_level=0.70,
        thesis_actionable=0.80,
        disagreement_severity="severe",
    )
    res = trading_gates_policy(q_split, config)
    assert res["decision"] == "escalate"
    assert res["execution_action"] == "escalate_to_human"

    # Borderline actionability -> reduce
    q_borderline = ThesisQualityQuestions(
        analyst_agreement=0.80,
        conviction_level=0.75,
        thesis_actionable=0.60,
        disagreement_severity="minor",
    )
    res = trading_gates_policy(q_borderline, config)
    assert res["decision"] == "reduce"


def test_gate4_multi_asset_risk_compliance(config):
    # 1. Clean Stock
    q_clean = RiskComplianceQuestions(
        violates_position_limit=0.0,
        violates_max_loss=0.0,
        violates_concentration=0.0,
        acceptable_risk_reward=0.85,
    )
    stock_ctx = {
        "asset_class": AssetClass.STOCK,
        "details": {"beta": 1.4, "market_cap": 2e11},
    }
    res = trading_gates_policy(q_clean, config, asset_context=stock_ctx)
    assert res["decision"] == "proceed"

    # 2. Stock Beta Exceeded
    bad_beta_ctx = {
        "asset_class": AssetClass.STOCK,
        "details": {"beta": 3.8, "market_cap": 2e11},
    }
    res = trading_gates_policy(q_clean, config, asset_context=bad_beta_ctx)
    assert res["decision"] == "reject"
    assert any("beta" in r.lower() for r in res["reasons"])

    # 3. Bond Duration Exceeded
    bad_bond_ctx = {
        "asset_class": AssetClass.BOND,
        "details": {"duration": 18.0, "credit_rating": "AA"},
    }
    res = trading_gates_policy(q_clean, config, asset_context=bad_bond_ctx)
    assert res["decision"] == "reject"
    assert any("duration" in r.lower() for r in res["reasons"])

    # 4. Option Greeks Delta Exceeded
    bad_option_ctx = {
        "asset_class": AssetClass.OPTION,
        "details": {"delta": 0.85, "expiration_days": 20, "vega": 50.0},
    }
    res = trading_gates_policy(q_clean, config, asset_context=bad_option_ctx)
    assert res["decision"] == "reject"
    assert any("delta" in r.lower() for r in res["reasons"])

    # 5. Forex Excessive Pip Risk
    bad_fx_ctx = {
        "asset_class": AssetClass.FOREX,
        "stop_loss_pips": 120.0,
        "details": {"leverage": 20.0},
    }
    res = trading_gates_policy(q_clean, config, asset_context=bad_fx_ctx)
    assert res["decision"] == "reject"
    assert any("pip" in r.lower() for r in res["reasons"])

    # 6. Low Risk/Reward -> Reduce Size
    q_low_rr = RiskComplianceQuestions(
        violates_position_limit=0.0,
        violates_max_loss=0.0,
        violates_concentration=0.0,
        acceptable_risk_reward=0.55,
    )
    res = trading_gates_policy(q_low_rr, config, asset_context=stock_ctx)
    assert res["decision"] == "reduce"
