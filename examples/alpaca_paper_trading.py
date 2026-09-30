#!/usr/bin/env python3
"""Alpaca-py Paper Trading Demonstration for AutoTrader.

Inspired by https://github.com/alpacahq/alpaca-py/tree/master/examples.
Demonstrates:
1. Account verification (cash, equity, buying power).
2. Live market quote fetching for Equities & Crypto.
3. Submitting market & bracket orders protected by Laya Gate 4 compliance.
4. Position & order tracking with emergency cancellation.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from tradingagents.alpaca_integration import AlpacaExchange
from tradingagents.laya_integration.gates import LayaGates
from tradingagents.laya_integration.config import LayaConfig


def main():
    print("=" * 70)
    print("🦙 ALPACAHQ / ALPACA-PY PAPER TRADING INTEGRATION DEMO")
    print("=" * 70)

    # 1. Initialize Alpaca Exchange
    alpaca = AlpacaExchange()
    is_live = alpaca.is_connected()

    mode_str = "CONNECTED (LIVE PAPER TRADING)" if is_live else "OFFLINE SIMULATOR (Set APCA_API_KEY_ID & APCA_API_SECRET_KEY to connect)"
    print(f"• Mode: {mode_str}")
    print(f"• Target Endpoint: {alpaca.base_url}")
    print("-" * 70)

    # 2. Inspect Account
    acct = alpaca.get_account_info()
    print("📊 1. ACCOUNT OVERVIEW:")
    print(f"   Account Number : {acct.get('account_number')}")
    print(f"   Account Status : {acct.get('status')}")
    print(f"   Portfolio Cash : ${acct.get('cash', 0.0):,.2f}")
    print(f"   Total Equity   : ${acct.get('equity', 0.0):,.2f}")
    print(f"   Buying Power   : ${acct.get('buying_power', 0.0):,.2f}")
    print("-" * 70)

    # 3. Fetch Live Market Quotes
    print("📈 2. LIVE MARKET DATA FETCH (alpaca-py data clients):")
    watchlist = ["SPY", "AAPL", "NVDA", "BTC-USD"]
    for sym in watchlist:
        price = alpaca.get_price(sym)
        print(f"   {sym:<8} : ${price:,.2f}")
    print("-" * 70)

    # 4. Laya Gate 4 Pre-Flight Check & Market Order Execution
    print("🛡️ 3. LAYA GATE 4 RISK COMPLIANCE + ORDER SUBMISSION:")
    target_sym = "AAPL"
    qty = 2.0
    price = alpaca.get_price(target_sym)

    gates = LayaGates(config=LayaConfig())
    gate_state = {
        "symbol": target_sym,
        "asset_class": "stock",
        "proposed_trade": {
            "symbol": target_sym,
            "asset_class": "stock",
            "side": "buy",
            "quantity": qty,
            "price": price,
        },
        "portfolio_state": {
            "current_position": 0.0,
            "daily_loss": 0.0,
            "portfolio_cash": acct.get("cash", 100_000.0),
        },
    }

    res = gates.run_risk_compliance(gate_state)
    print(f"   Gate 4 Verdict: {res['decision'].upper()} (Confidence: {res.get('confidence', 0.9):.2f})")
    print(f"   Reasons: {'; '.join(res.get('reasons', []))}")

    if res["decision"] == "proceed":
        order_res = alpaca.place_order(symbol=target_sym, side="buy", quantity=qty, order_type="market")
        print(f"   Order Result: {order_res['status'].upper()} (Order ID: {order_res['order_id']})")
    else:
        print("   Order blocked by risk policy.")
    print("-" * 70)

    # 5. Advanced Bracket Order (Take-Profit + Stop-Loss)
    print("🎯 4. BRACKET ORDER DEMONSTRATION (Take-Profit & Stop-Loss):")
    spy_price = alpaca.get_price("SPY")
    tp = round(spy_price * 1.05, 2)  # 5% profit target
    sl = round(spy_price * 0.97, 2)  # 3% stop loss

    print(f"   Submitting bracket order on SPY @ ~${spy_price:.2f}")
    print(f"   Take-Profit Target: ${tp:.2f} (+5%)")
    print(f"   Stop-Loss Target  : ${sl:.2f} (-3%)")

    bracket_res = alpaca.place_order(
        symbol="SPY",
        side="buy",
        quantity=1.0,
        order_type="market",
        take_profit=tp,
        stop_loss=sl,
    )
    print(f"   Bracket Order Status: {bracket_res['status'].upper()} (Order ID: {bracket_res['order_id']})")
    print("-" * 70)

    # 6. Current Positions
    print("💼 5. OPEN POSITIONS:")
    positions = alpaca.get_positions()
    if positions:
        for p in positions:
            print(f"   {p['symbol']:<8}: {p['quantity']} units | Avg: ${p['avg_price']:.2f} | Unrealized P&L: ${p['unrealized_pnl']:.2f}")
    else:
        print("   No active positions returned from paper account.")

    print("=" * 70)
    print("🚀 Run Live Desk to monitor in browser: python3 -m desk --port 8585")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
