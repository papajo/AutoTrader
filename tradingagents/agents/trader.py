"""Trader Agent: Synthesizes multi-agent consensus and drafts asset-specific orders."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from tradingagents.laya_integration.schemas import AssetClass, ProposedTrade


class TraderAgent:
    """Drafts actionable trade orders based on multi-agent debate synthesis and risk parameters."""

    def __init__(self, name: str = "TraderAgent"):
        self.name = name

    def draft_order(
        self,
        state: Dict[str, Any],
        analyst_reports: Dict[str, Any],
        size_multiplier: float = 1.0,
    ) -> ProposedTrade:
        symbol = str(state.get("symbol", state.get("ticker", "NVDA")))
        raw_asset_class = state.get("asset_class", "stock")
        try:
            asset_class = AssetClass(str(raw_asset_class).lower())
        except (ValueError, TypeError):
            asset_class = AssetClass.STOCK

        price = float(state.get("price", 100.0))
        portfolio_val = float(state.get("portfolio_value", 10000.0))

        # Evaluate directional consensus
        directions = [
            rep.get("direction", "neutral")
            for rep in analyst_reports.values()
            if isinstance(rep, dict)
        ]
        buy_votes = directions.count("buy")
        sell_votes = directions.count("sell")

        if buy_votes > sell_votes:
            side = "buy"
        elif sell_votes > buy_votes:
            side = "sell"
        else:
            side = "hold"

        # Position sizing tailored per asset class
        base_risk_pct = 0.05  # 5% max risk allocation
        target_allocation = portfolio_val * base_risk_pct * size_multiplier

        if asset_class == AssetClass.FOREX:
            # Forex lot sizing (e.g. 0.1 lots = 10,000 units)
            quantity = round(max(0.01, (target_allocation / 1000.0)), 2)
            stop_loss = round(price - 0.0030 if side == "buy" else price + 0.0030, 5)
            take_profit = round(price + 0.0060 if side == "buy" else price - 0.0060, 5)
        elif asset_class == AssetClass.OPTION:
            # Option contracts (1 contract = 100 shares)
            contract_cost = max(1.0, price * 100.0)
            quantity = max(1.0, round(target_allocation / contract_cost))
            stop_loss = round(price * 0.70, 2)
            take_profit = round(price * 1.50, 2)
        elif asset_class == AssetClass.BOND:
            # Bond units (often par value $1,000)
            bond_price = price if price > 500 else 1000.0
            quantity = max(1.0, round(target_allocation / bond_price))
            stop_loss = round(bond_price * 0.96, 2)
            take_profit = round(bond_price * 1.06, 2)
        else:
            # Equities, Commodities, ETFs, Mutual Funds
            quantity = max(1.0, round(target_allocation / max(1.0, price)))
            stop_loss = round(price * 0.95 if side == "buy" else price * 1.05, 2)
            take_profit = round(price * 1.10 if side == "buy" else price * 0.90, 2)

        estimated_val = quantity * price

        rationale = (
            f"Multi-agent consensus ({buy_votes} buy, {sell_votes} sell) "
            f"warrants a {side.upper()} order for {quantity} units of {symbol} ({asset_class.value}) "
            f"at ${price:.2f}."
        )

        return ProposedTrade(
            symbol=symbol,
            asset_class=asset_class,
            side=side,
            quantity=quantity,
            price=price,
            estimated_value=estimated_val,
            stop_loss=stop_loss,
            take_profit=take_profit,
            details=state.get("details", state.get("asset_details")),
            rationale=rationale,
        )
