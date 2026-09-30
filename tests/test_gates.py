"""Unit tests for LangChain Runnable gate nodes and LayaGates orchestrator."""

import pytest
from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.gates import (
    LayaGates,
    PreflightGate,
    NewsRiskGate,
    ThesisQualityGate,
    RiskComplianceGate,
)
from tradingagents.laya_integration.router import LayaRouter


@pytest.fixture
def laya_gates():
    cfg = LayaConfig()
    return LayaGates(config=cfg)


def test_gate_runnable_interface(laya_gates):
    preflight = laya_gates.preflight
    state = {
        "symbol": "AAPL",
        "asset_class": "stock",
        "volatility": 0.22,
        "price_change_20d": 0.04,
    }

    # Test .run()
    res1 = preflight.run(state)
    assert res1["decision"] == "proceed"
    assert "latency_ms" in res1

    # Test LangChain .invoke()
    res2 = preflight.invoke(state)
    assert res2["decision"] == res1["decision"]

    # Test LangChain .batch()
    batch_res = preflight.batch([state, state])
    assert len(batch_res) == 2
    assert batch_res[0]["decision"] == "proceed"


def test_gate_disabled_bypass():
    cfg = LayaConfig(enabled=True, preflight_regime_gate=False)
    gates = LayaGates(config=cfg)

    # Preflight should bypass with latency 0 and decision proceed
    res = gates.run_preflight({"symbol": "AAPL", "volatility": 0.99, "market_crisis_signal": True})
    assert res["decision"] == "proceed"
    assert res["router_used"] == "bypass"


def test_all_four_gates_sequential(laya_gates):
    state = {
        "symbol": "NVDA",
        "asset_class": "stock",
        "volatility": 0.25,
        "price_change_20d": 0.05,
        "news_event_type": "earnings",
        "sentiment_score": 0.80,
        "analyst_agreement": 0.90,
        "conviction_level": 0.85,
        "thesis_actionable": 0.90,
        "violates_position_limit": 0.0,
        "violates_max_loss": 0.0,
        "violates_concentration": 0.0,
        "acceptable_risk_reward": 0.88,
    }

    g1 = laya_gates.run_preflight(state)
    assert g1["decision"] == "proceed"

    g2 = laya_gates.run_news_risk(state)
    assert g2["decision"] == "proceed"

    g3 = laya_gates.run_thesis_quality(state)
    assert g3["decision"] == "proceed"

    g4 = laya_gates.run_risk_compliance(state)
    assert g4["decision"] == "proceed"
