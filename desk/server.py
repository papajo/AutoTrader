"""FastAPI backend server for the AutoTrader Live Execution Desk."""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.gates import LayaGates
from tradingagents.alpaca_integration import AlpacaExchange

logger = logging.getLogger("DeskServer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
AUDIT_LOG_PATH = BASE_DIR / "audit_trail.jsonl"
REPORTS_OUT_DIR = BASE_DIR / "reports" / "out"


class OrderRequest(BaseModel):
    symbol: str
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., gt=0)
    asset_class: str = "stock"
    order_type: str = "market"
    validate_laya: bool = True


class ConfigUpdateRequest(BaseModel):
    max_daily_loss: Optional[float] = None
    trade_cooldown: Optional[int] = None
    max_position_size: Optional[float] = None


class ConnectionManager:
    """Manages active WebSocket connections for live desk broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        data_text = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(data_text)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                self.disconnect(connection)


class LiveDeskState:
    """In-memory state and trade coordinator for the Live Desk."""

    def __init__(self):
        self.is_running = True
        self.is_killed = False
        self.portfolio_cash = 100_000.0
        self.initial_capital = 100_000.0
        self.realized_pnl = 0.0
        self.daily_loss = 0.0
        self.max_daily_loss = 1_000.0
        self.trade_cooldown = 30
        self.max_position_size = 50_000.0
        self.laya_gates_enabled = True

        # Multi-asset watchlists with base reference prices
        self.tickers: Dict[str, Dict[str, Any]] = {
            "SPY": {"symbol": "SPY", "name": "S&P 500 ETF", "price": 552.40, "change_pct": +0.42, "high": 554.10, "low": 550.80, "volume": "48.2M", "asset_class": "etf"},
            "AAPL": {"symbol": "AAPL", "name": "Apple Inc.", "price": 226.75, "change_pct": +1.15, "high": 227.90, "low": 224.50, "volume": "32.1M", "asset_class": "stock"},
            "NVDA": {"symbol": "NVDA", "name": "Nvidia Corp.", "price": 128.50, "change_pct": -0.85, "high": 131.20, "low": 127.40, "volume": "65.4M", "asset_class": "stock"},
            "BTC-USD": {"symbol": "BTC-USD", "name": "Bitcoin USD", "price": 64850.00, "change_pct": +2.34, "high": 65400.0, "low": 63900.0, "volume": "28.4K", "asset_class": "crypto"},
            "ETH-USD": {"symbol": "ETH-USD", "name": "Ethereum USD", "price": 2640.00, "change_pct": +1.80, "high": 2680.0, "low": 2590.0, "volume": "112.5K", "asset_class": "crypto"},
            "US10Y": {"symbol": "US10Y", "name": "10-Year Treasury Yield", "price": 3.84, "change_pct": -0.02, "high": 3.87, "low": 3.82, "volume": "Benchmark", "asset_class": "bond"},
            "CL": {"symbol": "CL", "name": "Crude Oil WTI", "price": 72.35, "change_pct": -1.20, "high": 73.80, "low": 71.90, "volume": "210K", "asset_class": "commodity"},
            "GC": {"symbol": "GC", "name": "Gold Futures", "price": 2682.50, "change_pct": +0.65, "high": 2690.0, "low": 2671.0, "volume": "145K", "asset_class": "commodity"},
            "EURUSD": {"symbol": "EURUSD", "name": "Euro / US Dollar", "price": 1.1145, "change_pct": +0.12, "high": 1.1168, "low": 1.1130, "volume": "Spot FX", "asset_class": "forex"},
        }

        # Seed positions
        self.positions: Dict[str, Dict[str, Any]] = {
            "SPY": {
                "symbol": "SPY",
                "asset_class": "etf",
                "quantity": 50.0,
                "avg_price": 548.20,
                "current_price": 552.40,
                "market_value": 27620.0,
                "unrealized_pnl": 210.0,
                "unrealized_pnl_pct": 0.76,
            },
            "BTC-USD": {
                "symbol": "BTC-USD",
                "asset_class": "crypto",
                "quantity": 0.25,
                "avg_price": 63900.0,
                "current_price": 64850.0,
                "market_value": 16212.5,
                "unrealized_pnl": 237.5,
                "unrealized_pnl_pct": 1.48,
            },
        }

        # Order history
        self.orders: List[Dict[str, Any]] = []

        # Gate coordinator
        self.laya_gates = LayaGates(config=LayaConfig())

        # Alpaca Paper Trading Client
        self.alpaca = AlpacaExchange()
        if self.alpaca.is_connected():
            acct = self.alpaca.get_account_info()
            self.portfolio_cash = acct.get("cash", self.portfolio_cash)
            self.initial_capital = acct.get("equity", self.initial_capital)
            alp_pos = self.alpaca.get_positions()
            if alp_pos:
                self.positions = {p["symbol"]: p for p in alp_pos}

    def get_unrealized_pnl(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            sym = pos["symbol"]
            curr = self.tickers.get(sym, {}).get("price", pos["avg_price"])
            pnl = (curr - pos["avg_price"]) * pos["quantity"]
            total += pnl
        return round(total, 2)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        unrealized = self.get_unrealized_pnl()
        invested = sum(pos["quantity"] * self.tickers.get(pos["symbol"], {}).get("price", pos["avg_price"]) for pos in self.positions.values())
        nav = self.portfolio_cash + invested
        total_pnl = self.realized_pnl + unrealized
        alpaca_info = self.alpaca.get_account_info()
        return {
            "net_account_value": round(nav, 2) if not self.alpaca.is_connected() else alpaca_info.get("equity", round(nav, 2)),
            "cash": round(self.portfolio_cash, 2) if not self.alpaca.is_connected() else alpaca_info.get("cash", round(self.portfolio_cash, 2)),
            "invested": round(invested, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(total_pnl, 2),
            "daily_loss": round(self.daily_loss, 2),
            "max_daily_loss": self.max_daily_loss,
            "status": "HALTED" if self.is_killed else ("RUNNING" if self.is_running else "PAUSED"),
            "open_positions_count": len(self.positions),
            "open_orders_count": len([o for o in self.orders if o.get("status") == "pending"]),
            "alpaca_connected": self.alpaca.is_connected(),
            "alpaca_account": alpaca_info.get("account_number", "SIMULATED"),
            "alpaca_status": alpaca_info.get("status", "SIMULATED"),
            "alpaca_buying_power": alpaca_info.get("buying_power", 200_000.0),
            "alpaca_base_url": self.alpaca.base_url,
        }

    def update_ticks(self) -> List[Dict[str, Any]]:
        """Simulate realistic continuous price changes and recalculate position P&L."""
        updated = []
        for sym, t in self.tickers.items():
            drift_pct = (random.random() - 0.495) * 0.003
            old_p = t["price"]
            if t["asset_class"] == "bond":
                new_p = max(0.01, round(old_p + (random.random() - 0.5) * 0.01, 2))
            elif t["asset_class"] == "forex":
                new_p = max(0.1, round(old_p * (1.0 + drift_pct * 0.2), 4))
            elif t["asset_class"] == "crypto":
                new_p = max(1.0, round(old_p * (1.0 + drift_pct * 1.8), 2))
            else:
                new_p = max(1.0, round(old_p * (1.0 + drift_pct), 2))

            t["price"] = new_p
            t["change_pct"] = round(((new_p - old_p) / old_p) * 100 + t.get("change_pct", 0.0) * 0.99, 2)
            t["high"] = max(t["high"], new_p)
            t["low"] = min(t["low"], new_p)

            # Update position mark-to-market if open
            if sym in self.positions:
                pos = self.positions[sym]
                pos["current_price"] = new_p
                pos["market_value"] = round(new_p * pos["quantity"], 2)
                pos["unrealized_pnl"] = round((new_p - pos["avg_price"]) * pos["quantity"], 2)
                pos["unrealized_pnl_pct"] = round(((new_p - pos["avg_price"]) / pos["avg_price"]) * 100, 2)

            updated.append(t)
        return updated

    def execute_order(self, req: OrderRequest) -> Dict[str, Any]:
        """Process an order with optional Laya Gate 4 compliance check."""
        if self.is_killed:
            raise HTTPException(status_code=400, detail="Trading is HALTED via Emergency Kill Switch.")

        sym = req.symbol.upper()
        price = self.tickers.get(sym, {}).get("price", 100.0)
        cost = price * req.quantity

        # Laya Gate 4 Risk Compliance check
        gate_decision = None
        if req.validate_laya and self.laya_gates_enabled:
            state = {
                "symbol": sym,
                "asset_class": req.asset_class,
                "proposed_trade": {
                    "symbol": sym,
                    "asset_class": req.asset_class,
                    "side": req.side,
                    "quantity": req.quantity,
                    "price": price,
                },
                "portfolio_state": {
                    "current_position": self.positions.get(sym, {}).get("quantity", 0.0),
                    "daily_loss": self.daily_loss,
                    "portfolio_cash": self.portfolio_cash,
                },
            }
            gate_res = self.laya_gates.run_risk_compliance(state)
            gate_decision = gate_res

            # Append to audit trail
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gate_name": "RiskComplianceGate",
                "symbol": sym,
                "asset_class": req.asset_class,
                "decision": gate_res["decision"],
                "confidence": gate_res.get("confidence", 0.9),
                "reasons": gate_res.get("reasons", []),
                "execution_action": gate_res.get("execution_action", "execute_order"),
                "latency_ms": gate_res.get("latency_ms", 0.01),
                "router_used": "laya",
                "laya_answers": gate_res.get("laya_answers", {}),
            }
            try:
                with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to append to audit log: {e}")

            if gate_res["decision"] == "reject":
                order_rec = {
                    "order_id": f"ORD-{int(time.time()*1000)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": sym,
                    "side": req.side,
                    "quantity": req.quantity,
                    "price": price,
                    "status": "rejected",
                    "reason": "; ".join(gate_res.get("reasons", ["Rejected by Laya Gate 4"])),
                    "gate_decision": gate_decision,
                }
                self.orders.insert(0, order_rec)
                return order_rec

        # Execute fill via Alpaca Paper Trading if connected, else simulator
        if self.alpaca.is_connected():
            try:
                alp_res = self.alpaca.place_order(
                    symbol=sym,
                    side=req.side,
                    quantity=req.quantity,
                    order_type=req.order_type,
                )
                # Synchronize live positions & account balance
                alp_positions = self.alpaca.get_positions()
                self.positions = {p["symbol"]: p for p in alp_positions}
                acct = self.alpaca.get_account_info()
                self.portfolio_cash = acct.get("cash", self.portfolio_cash)

                order_rec = {
                    "order_id": alp_res.get("order_id", f"ALP-{int(time.time()*1000)}"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": sym,
                    "side": req.side,
                    "quantity": req.quantity,
                    "price": alp_res.get("price", price),
                    "status": alp_res.get("status", "filled"),
                    "source": "alpaca_paper",
                    "reason": "Submitted to Alpaca Paper Trading",
                    "gate_decision": gate_decision,
                }
                self.orders.insert(0, order_rec)
                return order_rec
            except Exception as e:
                logger.error(f"Alpaca order submission failed: {e}")
                raise HTTPException(status_code=502, detail=f"Alpaca Paper Error: {e}")

        # Local Paper Simulator Fallback
        if req.side.lower() == "buy":
            if self.portfolio_cash < cost:
                raise HTTPException(status_code=400, detail=f"Insufficient cash: require ${cost:.2f}, have ${self.portfolio_cash:.2f}")
            self.portfolio_cash -= cost
            if sym in self.positions:
                cur_qty = self.positions[sym]["quantity"]
                cur_cost = self.positions[sym]["avg_price"] * cur_qty
                new_qty = cur_qty + req.quantity
                self.positions[sym]["avg_price"] = round((cur_cost + cost) / new_qty, 2)
                self.positions[sym]["quantity"] = round(new_qty, 4)
            else:
                self.positions[sym] = {
                    "symbol": sym,
                    "asset_class": req.asset_class,
                    "quantity": round(req.quantity, 4),
                    "avg_price": price,
                    "current_price": price,
                    "market_value": round(cost, 2),
                    "unrealized_pnl": 0.0,
                    "unrealized_pnl_pct": 0.0,
                }
        elif req.side.lower() == "sell":
            if sym not in self.positions or self.positions[sym]["quantity"] < req.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient position in {sym} to sell {req.quantity}")
            avg_p = self.positions[sym]["avg_price"]
            pnl = (price - avg_p) * req.quantity
            self.realized_pnl += pnl
            self.portfolio_cash += cost
            rem_qty = round(self.positions[sym]["quantity"] - req.quantity, 4)
            if rem_qty <= 0.0001:
                del self.positions[sym]
            else:
                self.positions[sym]["quantity"] = rem_qty

        order_rec = {
            "order_id": f"ORD-{int(time.time()*1000)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": sym,
            "side": req.side,
            "quantity": req.quantity,
            "price": price,
            "status": "filled",
            "source": "local_simulator",
            "reason": "Executed in Local Paper Simulator",
            "gate_decision": gate_decision,
        }
        self.orders.insert(0, order_rec)
        return order_rec

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Flatten an open position at current market price."""
        sym = symbol.upper()
        if sym not in self.positions:
            raise HTTPException(status_code=404, detail=f"No open position found for {sym}")
        pos = self.positions[sym]

        if self.alpaca.is_connected():
            self.alpaca.close_position(sym)
            alp_pos = self.alpaca.get_positions()
            self.positions = {p["symbol"]: p for p in alp_pos}
            order_rec = {
                "order_id": f"ALP-CLOSE-{int(time.time()*1000)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": sym,
                "side": "sell",
                "quantity": pos["quantity"],
                "price": self.get_price(sym) if hasattr(self, 'get_price') else pos.get("current_price", pos.get("avg_price", 100.0)),
                "status": "closed",
                "source": "alpaca_paper",
                "reason": "Flattened via Alpaca Paper Trading",
            }
            self.orders.insert(0, order_rec)
            return order_rec

        req = OrderRequest(
            symbol=sym,
            side="sell",
            quantity=pos["quantity"],
            asset_class=pos.get("asset_class", "stock"),
            validate_laya=False,
        )
        return self.execute_order(req)


def get_recent_gate_logs(limit: int = 25) -> List[Dict[str, Any]]:
    """Read the last N entries from audit_trail.jsonl."""
    if not AUDIT_LOG_PATH.exists():
        return []
    lines: List[str] = []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Error reading audit log: {e}")
        return []

    results = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if line:
            try:
                results.append(json.loads(line))
            except Exception:
                continue
    return results


def create_app() -> FastAPI:
    """Create and configure the FastAPI Live Desk application."""
    desk_state = LiveDeskState()
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Background asynchronous task simulating real-time market drift and broadcasting."""
        async def ticker_loop():
            while True:
                try:
                    await asyncio.sleep(1.2)
                    ticks = desk_state.update_ticks()
                    summary = desk_state.get_portfolio_summary()
                    if manager.active_connections:
                        await manager.broadcast({
                            "type": "market_tick",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "tickers": ticks,
                            "summary": summary,
                        })
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in background ticker loop: {e}")
                    await asyncio.sleep(2)

        task = asyncio.create_task(ticker_loop())
        yield
        task.cancel()

    app = FastAPI(title="AutoTrader Live Execution Desk", version="2.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static backtest reports at /reports if available
    if REPORTS_OUT_DIR.exists():
        app.mount("/reports", StaticFiles(directory=str(REPORTS_OUT_DIR), html=True), name="reports")

    # Serve static desk frontend assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def get_index():
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return JSONResponse({"status": "Desk UI not built yet", "summary": desk_state.get_portfolio_summary()})
        return FileResponse(index_file)

    @app.get("/api/state")
    async def get_state():
        return {
            "summary": desk_state.get_portfolio_summary(),
            "positions": list(desk_state.positions.values()),
            "orders": desk_state.orders[:20],
            "tickers": desk_state.tickers,
            "is_killed": desk_state.is_killed,
            "is_running": desk_state.is_running,
        }

    @app.get("/api/tickers")
    async def get_tickers():
        return desk_state.tickers

    @app.get("/api/gates/recent")
    async def get_gates():
        return get_recent_gate_logs(limit=25)

    @app.post("/api/override/order")
    async def place_manual_order(req: OrderRequest):
        res = desk_state.execute_order(req)
        # Broadcast order execution
        await manager.broadcast({
            "type": "order_event",
            "order": res,
            "summary": desk_state.get_portfolio_summary(),
            "positions": list(desk_state.positions.values()),
        })
        return res

    @app.post("/api/override/close-position")
    async def close_position_endpoint(data: Dict[str, str]):
        sym = data.get("symbol")
        if not sym:
            raise HTTPException(status_code=400, detail="Symbol is required")
        res = desk_state.close_position(sym)
        await manager.broadcast({
            "type": "order_event",
            "order": res,
            "summary": desk_state.get_portfolio_summary(),
            "positions": list(desk_state.positions.values()),
        })
        return res

    @app.get("/api/alpaca/status")
    async def get_alpaca_status():
        return desk_state.alpaca.get_account_info()

    @app.post("/api/override/kill-switch")
    async def trigger_kill_switch():
        desk_state.is_killed = True
        desk_state.is_running = False
        if desk_state.alpaca.is_connected():
            desk_state.alpaca.cancel_all_orders()
        await manager.broadcast({
            "type": "system_alert",
            "level": "critical",
            "message": "🚨 EMERGENCY KILL SWITCH ENGAGED! Automated execution and new orders HALTED. Any open orders cancelled.",
            "is_killed": True,
            "summary": desk_state.get_portfolio_summary(),
        })
        return {"status": "HALTED", "message": "Emergency kill switch engaged"}

    @app.post("/api/override/resume")
    async def resume_trading():
        desk_state.is_killed = False
        desk_state.is_running = True
        await manager.broadcast({
            "type": "system_alert",
            "level": "info",
            "message": "✅ Trading execution resumed.",
            "is_killed": False,
            "summary": desk_state.get_portfolio_summary(),
        })
        return {"status": "RUNNING", "message": "Trading resumed"}

    @app.post("/api/override/config")
    async def update_config(req: ConfigUpdateRequest):
        if req.max_daily_loss is not None:
            desk_state.max_daily_loss = req.max_daily_loss
        if req.trade_cooldown is not None:
            desk_state.trade_cooldown = req.trade_cooldown
        if req.max_position_size is not None:
            desk_state.max_position_size = req.max_position_size
        return {
            "max_daily_loss": desk_state.max_daily_loss,
            "trade_cooldown": desk_state.trade_cooldown,
            "max_position_size": desk_state.max_position_size,
        }

    @app.post("/api/engine/run-cycle")
    async def trigger_auto_cycle(data: Optional[Dict[str, Any]] = None):
        """Run an immediate multi-agent pipeline cycle on a given symbol."""
        sym = (data or {}).get("symbol", "NVDA").upper()
        asset_class = (data or {}).get("asset_class", "stock")

        # Step 1: Preflight Gate
        p_res = desk_state.laya_gates.run_preflight({
            "symbol": sym,
            "market_trend": "uptrend",
            "volatility": 0.28,
            "spread_bps": 2.1,
            "macro_events_today": 0,
        })

        # Step 2: News Risk Gate
        n_res = desk_state.laya_gates.run_news_risk({
            "symbol": sym,
            "headline": f"{sym} announces strategic cloud expansion merger",
            "event_type": "M&A",
            "macro_impact": "low",
            "signal_quality": 0.88,
        })

        # Step 3: Thesis Quality Gate
        t_res = desk_state.laya_gates.run_thesis_quality({
            "symbol": sym,
            "analyst_theses": [
                {"role": "Technical", "action": "buy", "conviction": 0.85},
                {"role": "Fundamentals", "action": "buy", "conviction": 0.90},
                {"role": "Sentiment", "action": "buy", "conviction": 0.80},
                {"role": "Macro", "action": "buy", "conviction": 0.75},
            ]
        })

        # Step 4: Risk Compliance Gate
        r_res = desk_state.laya_gates.run_risk_compliance({
            "symbol": sym,
            "asset_class": asset_class,
            "proposed_trade": {
                "symbol": sym,
                "asset_class": asset_class,
                "side": "buy",
                "quantity": 10.0,
                "price": desk_state.tickers.get(sym, {}).get("price", 128.5),
            },
            "portfolio_state": {
                "current_position": desk_state.positions.get(sym, {}).get("quantity", 0.0),
                "daily_loss": desk_state.daily_loss,
            }
        })

        # Log and broadcast
        cycle_result = {
            "symbol": sym,
            "preflight": p_res,
            "news_risk": n_res,
            "thesis_quality": t_res,
            "risk_compliance": r_res,
            "approved": (
                p_res["decision"] == "proceed"
                and n_res["decision"] == "proceed"
                and t_res["decision"] == "proceed"
                and r_res["decision"] == "proceed"
            ),
        }

        # Append Gate 4 result to audit log
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gate_name": "ThesisQualityGate",
            "symbol": sym,
            "asset_class": asset_class,
            "decision": t_res["decision"],
            "confidence": t_res.get("confidence", 0.92),
            "reasons": t_res.get("reasons", ["All analysts aligned"]),
            "execution_action": t_res.get("execution_action", "continue_to_trader"),
            "latency_ms": t_res.get("latency_ms", 0.01),
            "router_used": "laya",
            "laya_answers": t_res.get("laya_answers", {}),
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        await manager.broadcast({
            "type": "cycle_completed",
            "cycle": cycle_result,
            "recent_gates": get_recent_gate_logs(10),
        })

        return cycle_result

    @app.websocket("/ws/live")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            # Send initial snapshot
            await websocket.send_text(json.dumps({
                "type": "initial_state",
                "summary": desk_state.get_portfolio_summary(),
                "positions": list(desk_state.positions.values()),
                "orders": desk_state.orders[:20],
                "tickers": list(desk_state.tickers.values()),
                "recent_gates": get_recent_gate_logs(15),
                "is_killed": desk_state.is_killed,
            }))
            while True:
                # Keep connection alive & listen for client messages
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    if payload.get("action") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))
                except Exception:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as e:
            logger.warning(f"WebSocket client error: {e}")
            manager.disconnect(websocket)

    return app


def start_desk_server(host: str = "127.0.0.1", port: int = 8585):
    """Start uvicorn server serving the Live Desk."""
    import uvicorn
    app = create_app()
    logger.info(f"Starting AutoTrader Live Execution Desk on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
