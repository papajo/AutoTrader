"""Unit tests for Laya and JEV non-autoregressive decision routers."""

import pytest
from tradingagents.laya_integration.config import LayaConfig, RouterType
from tradingagents.laya_integration.router import (
    LayaRouter,
    JEVRouter,
    UnifiedNonAutoregressiveRouter,
)
from tradingagents.laya_integration.schemas import (
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
)


def test_laya_router_prediction():
    router = LayaRouter()
    state = {
        "volatility": 0.20,
        "price_change_20d": 0.05,
    }
    answers, conf, meta = router.predict(state, MarketRegimeQuestions)
    assert isinstance(answers, MarketRegimeQuestions)
    assert answers.market_regime == "bullish"
    assert answers.market_trend == "uptrend"
    assert conf > 0.80
    assert meta["router"] == "laya"
    assert meta["latency_ms"] >= 0.0


def test_jev_router_prediction():
    router = JEVRouter()
    state = {
        "volatility": 0.85,
        "price_change_20d": -0.10,
    }
    answers, conf, meta = router.predict(state, MarketRegimeQuestions)
    assert isinstance(answers, MarketRegimeQuestions)
    assert answers.market_regime == "crisis"
    assert conf > 0.80
    assert meta["router"] == "jev"
    assert "energy_loss" in meta


def test_unified_router_fallback():
    # Configure hybrid router
    config = LayaConfig(
        router_type=RouterType.HYBRID,
    )
    # Set fallback confidence high to trigger fallback
    config.thresholds.laya_fallback_confidence = 0.99
    unified = UnifiedNonAutoregressiveRouter(config)

    state = {
        "volatility": 0.25,
        "price_change_20d": 0.02,
    }
    answers, conf, meta = unified.predict(state, MarketRegimeQuestions)
    # Because 0.99 > laya confidence (~0.89), it should fall back to JEV
    assert meta.get("fallback_triggered") is True
    assert meta.get("router") == "jev"


def test_unified_router_explicit_modes():
    config_laya = LayaConfig(router_type=RouterType.LAYA)
    unified_laya = UnifiedNonAutoregressiveRouter(config_laya)
    _, _, meta = unified_laya.predict({"volatility": 0.2}, MarketRegimeQuestions)
    assert meta["router"] == "laya"

    config_jev = LayaConfig(router_type=RouterType.JEV)
    unified_jev = UnifiedNonAutoregressiveRouter(config_jev)
    _, _, meta = unified_jev.predict({"volatility": 0.2}, MarketRegimeQuestions)
    assert meta["router"] == "jev"
