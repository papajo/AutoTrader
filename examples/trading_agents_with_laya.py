#!/usr/bin/env python3
"""TradingAgents + Laya/JEV Control Layer: Full Multi-Asset Demonstration.

Applicable for:
  - Stocks (Equities)
  - Bonds (Fixed Income)
  - Options (Greeks & Volatility)
  - Commodities (Futures & Contango/Backwardation)
  - ETFs (Index & Tracking)
  - Mutual Funds (NAV & Liquidity)
  - Forex (Currency Pairs & Pips)
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tradingagents.agents.workflow import LayaControlledTrading
from tradingagents.laya_integration.config import LayaConfig, RouterType
from tradingagents.laya_integration.gates import LayaGates
from tradingagents.laya_integration.schemas import (
    AssetClass,
    StockDetails,
    BondDetails,
    OptionDetails,
    CommodityDetails,
    ETFDetails,
    MutualFundDetails,
    ForexDetails,
)

# Setup clean console logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("LayaAutoTraderCLI")


def get_sample_asset_scenarios() -> Dict[str, Dict[str, Any]]:
    """Sample scenarios showcasing multi-asset coverage."""
    return {
        "stock": {
            "symbol": "NVDA",
            "asset_class": "stock",
            "price": 128.50,
            "portfolio_value": 50000.0,
            "price_change_20d": 0.08,
            "volatility": 0.32,
            "rsi": 62.0,
            "sma_50": 122.0,
            "sentiment_score": 0.78,
            "news_event_type": "earnings",
            "details": StockDetails(
                market_cap=3_100_000_000_000.0,
                beta=1.85,
                sector="Semiconductors",
                pe_ratio=42.5,
            ).model_dump(),
        },
        "bond": {
            "symbol": "US10Y",
            "asset_class": "bond",
            "price": 980.0,
            "portfolio_value": 100000.0,
            "price_change_20d": 0.01,
            "volatility": 0.12,
            "fed_stance": "dovish",
            "details": BondDetails(
                yield_to_maturity=0.0425,
                duration=7.8,
                convexity=0.65,
                credit_rating="AAA",
                coupon_rate=0.040,
                maturity_date="2036-05-15",
            ).model_dump(),
        },
        "option": {
            "symbol": "SPY260930C00550000",
            "asset_class": "option",
            "price": 6.80,
            "portfolio_value": 50000.0,
            "price_change_20d": 0.04,
            "volatility": 0.22,
            "details": OptionDetails(
                underlying_symbol="SPY",
                option_type="call",
                strike_price=550.0,
                expiration_days=25,
                implied_volatility=0.21,
                delta=0.42,
                gamma=0.03,
                vega=32.0,
                theta=-0.45,
            ).model_dump(),
        },
        "commodity": {
            "symbol": "CL_F",
            "asset_class": "commodity",
            "price": 74.20,
            "portfolio_value": 75000.0,
            "price_change_20d": 0.05,
            "volatility": 0.28,
            "details": CommodityDetails(
                commodity_type="energy",
                contract_month="CLX26",
                curve_state="backwardation",
                storage_rate=0.02,
                delivery_settlement="financial",
            ).model_dump(),
        },
        "etf": {
            "symbol": "QQQ",
            "asset_class": "etf",
            "price": 485.00,
            "portfolio_value": 60000.0,
            "price_change_20d": 0.06,
            "volatility": 0.24,
            "details": ETFDetails(
                benchmark_index="NASDAQ-100",
                expense_ratio=0.002,
                nav_premium_discount=0.001,
                leverage_factor=1.0,
                tracking_error=0.003,
            ).model_dump(),
        },
        "mutual_fund": {
            "symbol": "VFIAX",
            "asset_class": "mutual_fund",
            "price": 490.15,
            "portfolio_value": 80000.0,
            "price_change_20d": 0.03,
            "volatility": 0.16,
            "details": MutualFundDetails(
                nav=490.15,
                expense_ratio=0.0004,
                redemption_cutoff_time="16:00 EST",
                min_holding_days=30,
                turnover_ratio=0.02,
            ).model_dump(),
        },
        "forex": {
            "symbol": "EUR_USD",
            "asset_class": "forex",
            "price": 1.0850,
            "portfolio_value": 25000.0,
            "price_change_20d": 0.008,
            "volatility": 0.10,
            "details": ForexDetails(
                base_currency="EUR",
                quote_currency="USD",
                lot_size=100000.0,
                pip_value=10.0,
                spread_pips=1.1,
                leverage=30.0,
                interest_rate_differential=0.0125,
            ).model_dump(),
        },
    }


def run_single_scenario(
    name: str,
    state: Dict[str, Any],
    pipeline: LayaControlledTrading,
    date: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute a single scenario through the 4 Laya/JEV gates and multi-agent pipeline."""
    symbol = state.get("symbol", "UNKNOWN")
    asset_class = state.get("asset_class", "stock")

    print("\n" + "=" * 70)
    print(f"📊 TRADING AGENTS RUN: {symbol} ({asset_class.upper()}) | Date: {date}")
    print("=" * 70)

    result = pipeline.run_pipeline(dict(state))

    # Print Gate Execution details
    for gate_info in result.get("gates_executed", []):
        gate_name = gate_info["gate_name"]
        decision = gate_info["decision"]
        conf = gate_info["confidence"]
        router = gate_info["router_used"]
        lat = gate_info["latency_ms"]
        reasons = "; ".join(gate_info["reasons"])
        
        icon = {
            "proceed": "✅",
            "skip": "⏭️ [FAST-PATH SKIP]",
            "escalate": "⚠️ [ESCALATION]",
            "reduce": "📉 [SIZE REDUCED]",
            "reject": "❌ [RISK REJECTED]",
        }.get(decision, "ℹ️")

        print(f"[{gate_name}] Router: {router.upper()} ({lat:.1f}ms) | Conf: {conf:.2f}")
        print(f"   {icon} Decision: {decision.upper()} -> {reasons}")

    # Summary
    if result.get("pipeline_skipped"):
        print(f"\n⚡ Pipeline skipped! Expensive multi-agent LLM debate bypassed.")
        print(f"   Final Action: {result.get('final_action')} (Saved ~500ms - 2000ms latency & LLM cost)")
    elif result.get("human_escalated"):
        print(f"\n⚠️ Human Escalation Triggered! Analyst conflict requires manual sign-off.")
    elif result.get("trade_approved"):
        order = result.get("order", {})
        print(f"\n🎯 Trade APPROVED by all 4 gates!")
        print(f"   Order: {order.get('side', '').upper()} {order.get('quantity')} {order.get('symbol')} "
              f"at ${order.get('price', 0.0):.2f} (Est Value: ${order.get('estimated_value', 0.0):,.2f})")
        print(f"   Stop Loss: ${order.get('stop_loss', 0.0):.2f} | Take Profit: ${order.get('take_profit', 0.0):.2f}")
        print(f"   Rationale: {order.get('rationale')}")
    else:
        print(f"\n❌ Trade Rejected by Risk Compliance Gate.")
        print(f"   Reasons: {'; '.join(result.get('reasons', []))}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Smart AutoTrader: TradingAgents + Laya/JEV Control Layer")
    parser.add_argument("--ticker", type=str, default="NVDA", help="Asset ticker symbol")
    parser.add_argument("--asset-class", type=str, default="all",
                        choices=["stock", "bond", "option", "commodity", "etf", "mutual_fund", "forex", "all"],
                        help="Asset class to test")
    parser.add_argument("--date", type=str, default="2026-09-01", help="Trading simulation date")
    parser.add_argument("--router", type=str, default="hybrid", choices=["laya", "jev", "hybrid"],
                        help="Non-autoregressive router type")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate run without live execution")
    parser.add_argument("--config", type=str, default="config/autotrader_config.yaml", help="Path to config file")
    parser.add_argument("--demonstrate-skip", action="store_true", help="Simulate choppy/crisis regime to demonstrate skip")
    parser.add_argument("--demonstrate-escalation", action="store_true", help="Simulate analyst disagreement")
    parser.add_argument("--demonstrate-rejection", action="store_true", help="Simulate risk limit breach")
    args = parser.parse_args()

    # Load configuration
    try:
        config = LayaConfig.from_yaml(args.config)
    except FileNotFoundError:
        config = LayaConfig()

    config.router_type = RouterType(args.router)
    pipeline = LayaControlledTrading(config=config)
    scenarios = get_sample_asset_scenarios()

    print(f"🚀 Initializing Smart AutoTrader System")
    print(f"   Router Architecture: {config.router_type.value.upper()} (Non-Autoregressive ~33ms)")
    print(f"   Audit Log Path: {config.audit_log_path}")

    # Special demonstration modes
    if args.demonstrate_skip:
        print("\n🧪 DEMONSTRATION MODE: Simulating Choppy Market Regime...")
        choppy_state = dict(scenarios["stock"])
        choppy_state["volatility"] = 0.08
        choppy_state["price_change_20d"] = 0.005
        run_single_scenario("stock_choppy", choppy_state, pipeline, args.date, args.dry_run)
    elif args.demonstrate_escalation:
        print("\n🧪 DEMONSTRATION MODE: Simulating Analyst Disagreement...")
        escalate_state = dict(scenarios["stock"])
        escalate_state["_laya_answers"] = {
            "analyst_agreement": 0.40,
            "conviction_level": 0.55,
            "thesis_actionable": 0.50,
            "disagreement_severity": "severe",
        }
        run_single_scenario("stock_disagreement", escalate_state, pipeline, args.date, args.dry_run)
    elif args.demonstrate_rejection:
        print("\n🧪 DEMONSTRATION MODE: Simulating Risk Limit Breach (Excessive Option Delta/Vega)...")
        reject_state = dict(scenarios["option"])
        # Inject delta violation (> 0.50)
        reject_state["details"]["delta"] = 0.85
        reject_state["violates_position_limit"] = 0.85
        run_single_scenario("option_risk_violation", reject_state, pipeline, args.date, args.dry_run)
    elif args.asset_class == "all":
        print("\n🌐 Running Multi-Asset Universe Across All 7 Asset Classes...")
        for asset_name, asset_state in scenarios.items():
            run_single_scenario(asset_name, asset_state, pipeline, args.date, args.dry_run)
    else:
        state = scenarios.get(args.asset_class, scenarios["stock"])
        state["symbol"] = args.ticker
        run_single_scenario(args.asset_class, state, pipeline, args.date, args.dry_run)

    # Output Telemetry & Cost Savings Report
    metrics = pipeline.gates.get_metrics()
    print("\n" + "=" * 70)
    print("📈 AGGREGATE SYSTEM METRICS & SAVINGS SUMMARY")
    print("=" * 70)
    print(f"• Total Gate Decisions Executed : {metrics.get('total_decisions', 0)}")
    print(f"• Pipelines Requested           : {metrics.get('pipelines_requested', 0)}")
    print(f"• Pipelines Skipped (Fast-Path) : {metrics.get('pipelines_skipped', 0)} ({metrics.get('pipeline_skip_rate_pct', 0.0)}%)")
    print(f"• Estimated LLM Cost Saved      : ${metrics.get('cost_saved_usd', 0.0):.3f}")
    print(f"• Trades Executed               : {metrics.get('trades_executed', 0)}")
    print(f"• Trades Rejected               : {metrics.get('trades_rejected', 0)}")
    print(f"• Human Escalations             : {metrics.get('human_escalations', 0)}")
    print(f"• Router Usage Breakdown        : {json.dumps(metrics.get('router_usage', {}))}")
    print(f"• Gate Latencies (Avg)          : {json.dumps(metrics.get('avg_gate_latency_ms', {}))} ms")
    print(f"• Overall Gate Latency (Avg)    : {metrics.get('overall_avg_latency_ms', 0.0):.2f} ms")
    print(f"• Audit Trail File              : {config.audit_log_path} (100% auditable)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
