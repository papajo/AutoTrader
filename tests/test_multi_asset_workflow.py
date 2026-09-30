"""End-to-end integration tests for multi-asset workflow and TradingAgents debate."""

import pytest
from tradingagents.agents.workflow import LayaControlledTrading
from tradingagents.laya_integration.config import LayaConfig, RouterType
from tradingagents.laya_integration.schemas import AssetClass


@pytest.fixture
def workflow():
    config = LayaConfig()
    return LayaControlledTrading(config=config)


def test_equity_pipeline_approval(workflow):
    state = {
        "symbol": "NVDA",
        "asset_class": "stock",
        "price": 130.0,
        "portfolio_value": 50000.0,
        "price_change_20d": 0.06,
        "volatility": 0.28,
        "rsi": 60.0,
        "details": {"market_cap": 3e12, "beta": 1.7},
    }
    result = workflow.run_pipeline(state)
    assert result["trade_approved"] is True
    assert result["pipeline_skipped"] is False
    assert result["order"] is not None
    assert result["order"]["symbol"] == "NVDA"
    assert result["order"]["side"] == "buy"
    assert len(result["gates_executed"]) == 4


def test_choppy_regime_fast_path_skip(workflow):
    state = {
        "symbol": "AAPL",
        "asset_class": "stock",
        "price": 220.0,
        "price_change_20d": 0.005,
        "volatility": 0.09,
    }
    result = workflow.run_pipeline(state)
    assert result["pipeline_skipped"] is True
    assert result["trade_approved"] is False
    assert result["final_action"] == "hold"
    # Gate 1 should have fired and stopped the pipeline immediately
    assert len(result["gates_executed"]) == 1
    assert result["gates_executed"][0]["gate_name"] == "PreflightGate"


def test_bond_pipeline(workflow):
    state = {
        "symbol": "US10Y",
        "asset_class": "bond",
        "price": 990.0,
        "portfolio_value": 100000.0,
        "price_change_20d": 0.02,
        "volatility": 0.18,
        "details": {"duration": 7.5, "credit_rating": "AAA", "yield_to_maturity": 0.043},
    }
    result = workflow.run_pipeline(state)
    assert result["trade_approved"] is True
    assert result["order"]["asset_class"] == AssetClass.BOND


def test_junk_bond_rejection(workflow):
    state = {
        "symbol": "JUNK_CORP",
        "asset_class": "bond",
        "price": 850.0,
        "portfolio_value": 100000.0,
        "price_change_20d": 0.03,
        "volatility": 0.22,
        "details": {"duration": 5.0, "credit_rating": "CCC", "yield_to_maturity": 0.14},
    }
    result = workflow.run_pipeline(state)
    assert result["trade_approved"] is False
    # If analysts conflict (Fundamentals says sell, Technicals says buy), Gate 3 escalates
    # If it reaches Gate 4, Gate 4 rejects
    assert result["final_action"] in ("escalate_to_human", "trade_rejected")


def test_option_greeks_rejection(workflow):
    state = {
        "symbol": "SPY260930C",
        "asset_class": "option",
        "price": 5.50,
        "portfolio_value": 50000.0,
        "price_change_20d": 0.03,
        "volatility": 0.22,
        # Delta 0.90 violates max delta (0.50)
        "details": {"delta": 0.90, "expiration_days": 20, "vega": 40.0},
    }
    result = workflow.run_pipeline(state)
    assert result["trade_approved"] is False
    assert result["final_action"] == "trade_rejected"
    assert any("delta" in r.lower() for r in result["reasons"])


def test_analyst_conflict_escalation(workflow):
    state = {
        "symbol": "TSLA",
        "asset_class": "stock",
        "price": 240.0,
        "price_change_20d": 0.04,
        "volatility": 0.35,
        # Explicit mock answers triggering escalation
        "_laya_answers": {
            "analyst_agreement": 0.40,
            "conviction_level": 0.50,
            "thesis_actionable": 0.40,
            "disagreement_severity": "severe",
        },
    }
    result = workflow.run_pipeline(state)
    assert result["human_escalated"] is True
    assert result["trade_approved"] is False
    assert result["final_action"] == "escalate_to_human"
