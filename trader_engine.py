"""Trader Engine: Multi-Asset Autonomous Trading Execution Core with Laya & JEV Gate Integration."""

from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.gates import LayaGates
from tradingagents.laya_integration.schemas import AssetClass, ProposedTrade

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TraderEngine")


class ExchangeAPI(ABC):
    """Abstract base class for multi-asset exchange APIs."""

    @abstractmethod
    def get_price(self, symbol: str) -> float:
        """Fetch current market price for symbol."""
        pass

    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: float, **kwargs) -> bool:
        """Place an order with exchange."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass

    def get_asset_details(self, symbol: str) -> Dict[str, Any]:
        """Optional metadata hook for asset-specific parameters."""
        return {}


class Strategy(ABC):
    """Abstract base class for trading strategies."""

    @abstractmethod
    def generate_signal(self, price: float) -> str:
        """Return 'buy', 'sell', or '' for no action."""
        pass


class MultiAgentLayaStrategy(Strategy):
    """Strategy powered by TradingAgents multi-agent debate and Laya/JEV gates."""

    def __init__(self, laya_pipeline: Any):
        self.pipeline = laya_pipeline

    def generate_signal(self, price: float) -> str:
        state = {"price": price}
        result = self.pipeline.run_pipeline(state)
        if result.get("trade_approved") and result.get("order"):
            return result["order"]["side"]
        return ""


class TraderEngine:
    """Core autonomous trading engine with risk management and Laya/JEV gate verification."""

    def __init__(
        self,
        exchange: ExchangeAPI,
        strategy: Strategy,
        symbol: str,
        config: Union[str, Dict[str, Any]],
        asset_class: str = "stock",
        laya_gates: Optional[LayaGates] = None,
    ):
        self.exchange = exchange
        self.strategy = strategy
        self.symbol = symbol
        self.asset_class = asset_class
        self.position = 0.0
        self.pending_orders = []
        self.load_config(config)

        # Laya/JEV Non-Autoregressive Risk Gate integration
        self.laya_gates = laya_gates
        if self.laya_gates is None and self.config.get("laya_gates_enabled", False):
            l_cfg = LayaConfig()
            self.laya_gates = LayaGates(config=l_cfg)

    def load_config(self, config_or_path: Union[str, Dict[str, Any]]) -> None:
        """Load configuration from either a dictionary or a YAML file path."""
        if isinstance(config_or_path, dict):
            self.config = config_or_path
        else:
            import yaml
            with open(config_or_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

    def validate_risk_with_laya(self, side: str, price: float, quantity: float) -> bool:
        """Evaluate pre-trade risk via Laya Gate 4 (~33ms)."""
        if not self.laya_gates:
            return True

        asset_details = self.exchange.get_asset_details(self.symbol)
        state = {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "details": asset_details,
            "proposed_trade": {
                "symbol": self.symbol,
                "asset_class": self.asset_class,
                "side": side,
                "quantity": quantity,
                "price": price,
            },
            "portfolio_state": {
                "current_position": self.position,
                "daily_loss": self.config.get("daily_loss", 0.0),
            },
        }
        res = self.laya_gates.run_risk_compliance(state)
        if res["decision"] == "reject":
            logger.warning(f"Laya Gate 4 REJECTED trade: {'; '.join(res['reasons'])}")
            return False
        return True

    def validate_risk(self, signal: str, price: float) -> bool:
        """Check baseline risk parameters before executing trades."""
        daily_loss = self.config.get("daily_loss", 0.0)
        max_daily_loss = self.config.get("max_daily_loss", 500.0)
        if daily_loss >= max_daily_loss:
            logger.warning(f"Daily loss limit reached (${daily_loss} >= ${max_daily_loss})")
            return False
        return True

    def execute_trade(self, side: str, price: Optional[float] = None) -> bool:
        """Execute a trade order after passing risk and Laya gate checks."""
        qty = float(self.config.get("trade_quantity", 1.0))
        current_price = price if price is not None else self.exchange.get_price(self.symbol)

        # 1. Baseline risk validation
        if not self.validate_risk(side, current_price):
            return False

        # 2. Laya Gate 4 pre-flight compliance validation
        if not self.validate_risk_with_laya(side, current_price, qty):
            return False

        # 3. Order placement
        success = self.exchange.place_order(self.symbol, side, qty)
        if not success:
            logger.warning(f"Failed to place {side} order for {qty} {self.symbol}")
            return False

        if side.lower() == "buy":
            self.position += qty
        elif side.lower() == "sell":
            self.position -= qty

        logger.info(f"{side.capitalize()} order placed for {qty} {self.symbol} at ${current_price:.2f}. Position: {self.position}")
        return True

    def run(self, max_cycles: Optional[int] = None) -> None:
        """Main trading loop with strategy execution and sleep interval."""
        cycles = 0
        while True:
            try:
                price = self.exchange.get_price(self.symbol)
                logger.info(f"Current {self.symbol} price: {price}")

                signal = self.strategy.generate_signal(price)
                if signal in ("buy", "sell"):
                    self.execute_trade(signal, price=price)

                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break

                poll_int = self.config.get("poll_interval", 60)
                if poll_int > 0:
                    time.sleep(poll_int)
                else:
                    break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                time.sleep(self.config.get("trade_cooldown", 30))


if __name__ == "__main__":
    # Example mock run
    class MockExchange(ExchangeAPI):
        def get_price(self, symbol: str) -> float:
            return 42.0

        def place_order(self, symbol: str, side: str, quantity: float, **kwargs) -> bool:
            logger.info(f"Mock {side} order executed for {quantity} {symbol}")
            return True

        def cancel_order(self, order_id: str) -> bool:
            return True

    class SimpleStrategy(Strategy):
        def generate_signal(self, price: float) -> str:
            return "buy" if price < 50 else ""

    engine = TraderEngine(
        exchange=MockExchange(),
        strategy=SimpleStrategy(),
        symbol="BTC-USD",
        config="config.yaml",
    )
    engine.run(max_cycles=1)