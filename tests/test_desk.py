"""Unit and integration tests for the AutoTrader Live Execution Desk."""

import pytest
from fastapi.testclient import TestClient
from desk.server import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_desk_html_endpoint(client):
    """Verify that root endpoint serves the live desk HTML interface."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AUTOTRADER" in resp.text
    assert "LIVE EXECUTION DESK" in resp.text
    assert "EMERGENCY KILL SWITCH" in resp.text


def test_api_state(client):
    """Verify state endpoint returns valid portfolio summary and positions."""
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "positions" in data
    assert "tickers" in data
    assert data["summary"]["net_account_value"] > 0
    assert data["summary"]["status"] in ("RUNNING", "HALTED", "PAUSED")


def test_api_tickers(client):
    """Verify ticker watchlist contains stocks, bonds, crypto, commodities, forex."""
    resp = client.get("/api/tickers")
    assert resp.status_code == 200
    tickers = resp.json()
    assert "SPY" in tickers
    assert "AAPL" in tickers
    assert "BTC-USD" in tickers
    assert "US10Y" in tickers
    assert "CL" in tickers
    assert "EURUSD" in tickers
    assert tickers["SPY"]["price"] > 0


def test_api_recent_gates(client):
    """Verify recent gates endpoint returns a list of audit records."""
    resp = client.get("/api/gates/recent")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_manual_order_flow(client):
    """Test executing a manual order with Laya Gate 4 risk validation."""
    payload = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 5.0,
        "asset_class": "stock",
        "order_type": "market",
        "validate_laya": True,
    }
    resp = client.post("/api/override/order", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["side"] == "buy"
    assert data["quantity"] == 5.0
    assert data["status"] in ("filled", "rejected")

    # Verify updated positions in state
    state_resp = client.get("/api/state")
    symbols = [p["symbol"] for p in state_resp.json()["positions"]]
    if data["status"] == "filled":
        assert "AAPL" in symbols


def test_close_position(client):
    """Test flattening an open position."""
    # Seed position exists for SPY
    resp = client.post("/api/override/close-position", json={"symbol": "SPY"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "SPY"
    assert data["side"] == "sell"
    assert data["status"] == "filled"

    # Verify SPY is no longer in open positions
    state_resp = client.get("/api/state")
    symbols = [p["symbol"] for p in state_resp.json()["positions"]]
    assert "SPY" not in symbols


def test_kill_switch_and_resume(client):
    """Verify emergency kill switch halts trading and rejects subsequent orders."""
    # 1. Trigger Kill Switch
    halt_resp = client.post("/api/override/kill-switch")
    assert halt_resp.status_code == 200
    assert halt_resp.json()["status"] == "HALTED"

    # State check
    state_resp = client.get("/api/state")
    assert state_resp.json()["is_killed"] is True
    assert state_resp.json()["summary"]["status"] == "HALTED"

    # Order while halted should be blocked
    blocked_resp = client.post("/api/override/order", json={
        "symbol": "NVDA",
        "side": "buy",
        "quantity": 10.0,
        "asset_class": "stock",
    })
    assert blocked_resp.status_code == 400
    assert "HALTED" in blocked_resp.json()["detail"]

    # 2. Resume trading
    resume_resp = client.post("/api/override/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "RUNNING"

    # State check
    state_resp2 = client.get("/api/state")
    assert state_resp2.json()["is_killed"] is False
    assert state_resp2.json()["summary"]["status"] == "RUNNING"


def test_update_config(client):
    """Verify live updates to risk parameters."""
    resp = client.post("/api/override/config", json={
        "max_daily_loss": 2500.0,
        "trade_cooldown": 45,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_daily_loss"] == 2500.0
    assert data["trade_cooldown"] == 45


def test_run_auto_cycle(client):
    """Verify running an automated multi-agent cycle with 4 gates."""
    resp = client.post("/api/engine/run-cycle", json={"symbol": "NVDA", "asset_class": "stock"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "NVDA"
    assert "preflight" in data
    assert "news_risk" in data
    assert "thesis_quality" in data
    assert "risk_compliance" in data
    assert "approved" in data


def test_reports_static_mount(client):
    """Verify that strategy backtest reports are accessible from desk under /reports/."""
    resp = client.get("/reports/index.html")
    assert resp.status_code == 200
    assert "Autonomous AI Trading Agents" in resp.text
    assert "Agent 1: Opening Range Breakout" in resp.text
