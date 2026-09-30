"""Alpaca Markets Paper & Live Trading Integration for AutoTrader.

Implements ExchangeAPI for multi-asset paper trading via alpaca-py.
Supports account inspection, live market quotes, market/limit/bracket orders,
and emergency order cancellation.
"""

from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("AlpacaIntegration")

# Attempt importing alpaca-py SDK components
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        GetOrdersRequest,
        TakeProfitRequest,
        StopLossRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderType, QueryOrderStatus
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py package is not installed. Alpaca integration will run in mock/fallback mode.")


class AlpacaExchange:
    """ExchangeAPI implementation connecting to Alpaca Paper Trading."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
        self.base_url = (
            base_url
            or os.environ.get("APCA_API_BASE_URL")
            or "https://paper-api.alpaca.markets"
        )
        self.paper = paper or ("paper" in self.base_url.lower())

        self.trading_client: Optional[Any] = None
        self.stock_data_client: Optional[Any] = None
        self.crypto_data_client: Optional[Any] = None
        self._connected = False
        self._account_cache: Optional[Dict[str, Any]] = None

        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize alpaca-py client objects if credentials are valid."""
        if not ALPACA_AVAILABLE:
            logger.info("Alpaca SDK unavailable; running in offline simulation mode.")
            return

        if not self.api_key or not self.secret_key:
            logger.info("Alpaca API credentials not found. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY to enable live paper trading.")
            return

        try:
            self.trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            self.stock_data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
            self.crypto_data_client = CryptoHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
            # Verify connectivity by fetching account
            acct = self.trading_client.get_account()
            self._connected = True
            logger.info(f"✅ Connected to Alpaca Paper Trading (Account: {acct.account_number}, Status: {acct.status}, Buying Power: ${acct.buying_power})")
        except Exception as e:
            logger.warning(f"Failed to authenticate with Alpaca API ({e}). Running in offline simulation mode.")
            self._connected = False

    def is_connected(self) -> bool:
        """Return True if authenticated with Alpaca Paper API."""
        return self._connected

    def get_account_info(self) -> Dict[str, Any]:
        """Fetch real-time paper account metrics."""
        if not self._connected or not self.trading_client:
            return {
                "connected": False,
                "account_number": "SIMULATED",
                "status": "SIMULATED",
                "cash": 100_000.0,
                "equity": 100_000.0,
                "buying_power": 200_000.0,
                "portfolio_value": 100_000.0,
                "currency": "USD",
                "base_url": self.base_url,
            }

        try:
            acct = self.trading_client.get_account()
            return {
                "connected": True,
                "account_number": acct.account_number,
                "status": acct.status.value if hasattr(acct.status, "value") else str(acct.status),
                "cash": float(acct.cash),
                "equity": float(acct.equity),
                "buying_power": float(acct.buying_power),
                "portfolio_value": float(acct.portfolio_value),
                "currency": acct.currency,
                "base_url": self.base_url,
            }
        except Exception as e:
            logger.error(f"Error fetching Alpaca account: {e}")
            return {"connected": False, "error": str(e), "cash": 100_000.0, "equity": 100_000.0}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch all open positions from Alpaca Paper Account."""
        if not self._connected or not self.trading_client:
            return []

        try:
            positions = self.trading_client.get_all_positions()
            results = []
            for p in positions:
                results.append({
                    "symbol": p.symbol,
                    "asset_class": getattr(p, "asset_class", "stock"),
                    "quantity": float(p.qty),
                    "avg_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price) if p.current_price else float(p.avg_entry_price),
                    "market_value": float(p.market_value) if p.market_value else 0.0,
                    "unrealized_pnl": float(p.unrealized_pl) if p.unrealized_pl else 0.0,
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100 if p.unrealized_plpc else 0.0,
                    "side": getattr(p, "side", "long"),
                })
            return results
        except Exception as e:
            logger.error(f"Error fetching Alpaca positions: {e}")
            return []

    def get_price(self, symbol: str) -> float:
        """Fetch the latest price for a symbol using Alpaca Market Data."""
        clean_sym = symbol.upper().replace("-", "/")

        if self._connected:
            # 1. Try Crypto if '/' in symbol or standard crypto
            if "/" in clean_sym or clean_sym in ("BTC/USD", "ETH/USD"):
                try:
                    req = CryptoLatestQuoteRequest(symbol_or_symbols=clean_sym)
                    quotes = self.crypto_data_client.get_crypto_latest_quote(req)
                    if clean_sym in quotes:
                        q = quotes[clean_sym]
                        return float((q.bid_price + q.ask_price) / 2.0)
                except Exception as e:
                    logger.debug(f"Crypto quote failed for {clean_sym}: {e}")

            # 2. Try Equities
            if self.stock_data_client:
                try:
                    req = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
                    quotes = self.stock_data_client.get_stock_latest_quote(req)
                    if symbol.upper() in quotes:
                        q = quotes[symbol.upper()]
                        return float((q.bid_price + q.ask_price) / 2.0)
                except Exception as e:
                    logger.debug(f"Stock quote failed for {symbol}: {e}")

        # Fallback baseline prices
        baselines = {
            "SPY": 552.40,
            "AAPL": 226.75,
            "NVDA": 128.50,
            "BTC-USD": 64850.00,
            "ETH-USD": 2640.00,
            "US10Y": 3.84,
            "CL": 72.35,
            "GC": 2682.50,
            "EURUSD": 1.1145,
        }
        return baselines.get(symbol.upper(), 100.0)

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        time_in_force: str = "day",
        **kwargs,
    ) -> Dict[str, Any]:
        """Place an order with Alpaca Paper Trading. Supports market, limit, and bracket orders."""
        sym = symbol.upper()
        clean_sym = sym.replace("-", "/") if ("BTC" in sym or "ETH" in sym) else sym
        side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif_enum = TimeInForce.GTC if time_in_force.lower() == "gtc" else TimeInForce.DAY

        if not self._connected or not self.trading_client:
            # Fallback simulator fill
            current_p = self.get_price(sym)
            return {
                "order_id": f"SIM-{int(datetime.now(timezone.utc).timestamp()*1000)}",
                "symbol": sym,
                "side": side.lower(),
                "quantity": quantity,
                "price": limit_price or current_p,
                "status": "filled",
                "source": "simulator",
                "message": "Executed in AutoTrader Local Paper Simulator (Set Alpaca API keys to route to Alpaca).",
            }

        try:
            # Construct Bracket Parameters if requested
            tp_req = TakeProfitRequest(limit_price=round(take_profit, 2)) if take_profit else None
            sl_req = StopLossRequest(stop_price=round(stop_loss, 2)) if stop_loss else None

            if order_type.lower() == "limit" and limit_price is not None:
                req = LimitOrderRequest(
                    symbol=clean_sym,
                    qty=quantity,
                    side=side_enum,
                    time_in_force=tif_enum,
                    limit_price=round(limit_price, 2),
                    take_profit=tp_req,
                    stop_loss=sl_req,
                )
            else:
                req = MarketOrderRequest(
                    symbol=clean_sym,
                    qty=quantity,
                    side=side_enum,
                    time_in_force=tif_enum,
                    take_profit=tp_req,
                    stop_loss=sl_req,
                )

            order = self.trading_client.submit_order(order_data=req)
            logger.info(f"✅ Alpaca Paper Order Submitted: {order.id} | {side.upper()} {quantity} {clean_sym} ({order.status})")

            return {
                "order_id": str(order.id),
                "symbol": sym,
                "side": side.lower(),
                "quantity": float(order.qty) if order.qty else quantity,
                "price": float(order.filled_avg_price) if order.filled_avg_price else self.get_price(sym),
                "status": str(order.status.value if hasattr(order.status, "value") else order.status),
                "source": "alpaca_paper",
                "created_at": str(order.created_at),
                "alpaca_order": {
                    "id": str(order.id),
                    "client_order_id": getattr(order, "client_order_id", ""),
                    "type": str(order.type),
                }
            }
        except Exception as e:
            logger.error(f"Alpaca order placement failed: {e}")
            raise RuntimeError(f"Alpaca Paper API Error: {e}")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID."""
        if not self._connected or not self.trading_client:
            return True
        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info(f"Cancelled Alpaca order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Alpaca order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """Emergency order cancellation across all open paper orders."""
        if not self._connected or not self.trading_client:
            return True
        try:
            self.trading_client.cancel_orders()
            logger.warning("🚨 Alpaca: All open orders cancelled successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all Alpaca orders: {e}")
            return False

    def close_position(self, symbol: str) -> bool:
        """Close an open position at market price."""
        clean_sym = symbol.upper().replace("-", "/")
        if not self._connected or not self.trading_client:
            return True
        try:
            self.trading_client.close_position(clean_sym)
            logger.info(f"Closed Alpaca position in {clean_sym}")
            return True
        except Exception as e:
            logger.error(f"Failed to close Alpaca position {clean_sym}: {e}")
            return False
