"""Unit tests for Alpaca Markets Paper Trading integration."""

from unittest.mock import MagicMock, patch
import pytest
from tradingagents.alpaca_integration import AlpacaExchange
from desk.server import create_app
from fastapi.testclient import TestClient


def test_alpaca_exchange_offline_mode():
    """Verify offline fallback behavior when no API credentials are provided."""
    exchange = AlpacaExchange(api_key="", secret_key="")
    assert exchange.is_connected() is False
    acct = exchange.get_account_info()
    assert acct["connected"] is False
    assert acct["status"] == "SIMULATED"
    assert acct["cash"] == 100_000.0

    # Test price fetch
    price = exchange.get_price("SPY")
    assert price > 0.0

    # Test order placement in simulator fallback
    res = exchange.place_order("AAPL", "buy", 2.0)
    assert res["status"] == "filled"
    assert res["source"] == "simulator"
    assert res["symbol"] == "AAPL"


def test_alpaca_exchange_mocked_live_connection():
    """Verify TradingClient and DataClient interactions when authenticated."""
    with patch("tradingagents.alpaca_integration.TradingClient") as MockTradingClient, \
         patch("tradingagents.alpaca_integration.StockHistoricalDataClient") as MockDataClient:

        mock_trader = MagicMock()
        mock_data = MagicMock()
        MockTradingClient.return_value = mock_trader
        MockDataClient.return_value = mock_data

        # Mock account
        mock_acct = MagicMock()
        mock_acct.account_number = "PA12345678"
        mock_acct.status = "ACTIVE"
        mock_acct.cash = 45000.50
        mock_acct.equity = 65000.75
        mock_acct.buying_power = 90000.0
        mock_acct.portfolio_value = 65000.75
        mock_acct.currency = "USD"
        mock_trader.get_account.return_value = mock_acct

        # Mock positions
        mock_pos = MagicMock()
        mock_pos.symbol = "NVDA"
        mock_pos.qty = 15.0
        mock_pos.avg_entry_price = 120.0
        mock_pos.current_price = 128.5
        mock_pos.market_value = 1927.5
        mock_pos.unrealized_pl = 127.5
        mock_pos.unrealized_plpc = 0.0708
        mock_pos.asset_class = "stock"
        mock_trader.get_all_positions.return_value = [mock_pos]

        # Mock order submission
        mock_order = MagicMock()
        mock_order.id = "alp-order-999"
        mock_order.status = "new"
        mock_order.qty = 5.0
        mock_order.filled_avg_price = 128.50
        mock_order.created_at = "2026-09-30T12:00:00Z"
        mock_trader.submit_order.return_value = mock_order

        # Initialize exchange
        exchange = AlpacaExchange(api_key="test_key", secret_key="test_secret")
        assert exchange.is_connected() is True

        # Test account info
        info = exchange.get_account_info()
        assert info["connected"] is True
        assert info["account_number"] == "PA12345678"
        assert info["equity"] == 65000.75

        # Test positions
        positions = exchange.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "NVDA"
        assert positions[0]["quantity"] == 15.0

        # Test market order submission
        order_res = exchange.place_order(symbol="NVDA", side="buy", quantity=5.0)
        assert order_res["order_id"] == "alp-order-999"
        assert order_res["source"] == "alpaca_paper"
        assert mock_trader.submit_order.called

        # Test bracket order submission
        bracket_res = exchange.place_order(
            symbol="NVDA",
            side="buy",
            quantity=5.0,
            take_profit=140.0,
            stop_loss=115.0,
        )
        assert bracket_res["order_id"] == "alp-order-999"

        # Test cancel all orders
        assert exchange.cancel_all_orders() is True
        assert mock_trader.cancel_orders.called


def test_desk_alpaca_status_api():
    """Verify the /api/alpaca/status endpoint on the live desk server."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/alpaca/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "cash" in data
        assert "equity" in data
        assert "base_url" in data
