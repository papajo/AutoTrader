"""Audit trail logging and performance metrics tracking for Laya & JEV control gates."""

from __future__ import annotations
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from tradingagents.laya_integration.schemas import GateResult

logger = logging.getLogger("TradingAgents.Audit")


class AuditLogger:
    """Thread-safe structured audit logger for trading gate decisions."""

    def __init__(self, log_path: str = "audit_trail.jsonl"):
        self.log_path = log_path
        self._lock = threading.Lock()
        log_dir = os.path.dirname(os.path.abspath(log_path))
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def log_decision(
        self,
        gate_name: str,
        symbol: str,
        asset_class: str,
        result: GateResult,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a single gate decision to the persistent audit trail."""
        timestamp = datetime.now(timezone.utc).isoformat()
        entry: Dict[str, Any] = {
            "timestamp": timestamp,
            "gate_name": gate_name,
            "symbol": symbol,
            "asset_class": asset_class,
            "decision": result.decision,
            "confidence": round(result.confidence, 4),
            "reasons": result.reasons,
            "execution_action": result.execution_action,
            "latency_ms": round(result.latency_ms, 2),
            "router_used": result.router_used,
            "laya_answers": result.laya_answers,
        }
        if extra_metadata:
            entry["metadata"] = extra_metadata

        # Persist to JSONL file
        line = json.dumps(entry, default=str)
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        # Emit to standard logger
        status_icon = {
            "proceed": "✅",
            "skip": "⏭️",
            "hedge": "🛡️",
            "escalate": "⚠️",
            "reduce": "📉",
            "reject": "❌",
        }.get(result.decision, "ℹ️")

        logger.info(
            f"{status_icon} [{gate_name}] Symbol: {symbol} ({asset_class}) | "
            f"Decision: {result.decision.upper()} | Conf: {result.confidence:.2f} | "
            f"Router: {result.router_used} ({result.latency_ms:.1f}ms) | "
            f"Reason: {'; '.join(result.reasons[:2])}"
        )
        return entry

    def read_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Read recent audit records from disk."""
        if not os.path.exists(self.log_path):
            return []
        logs = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return logs[-limit:]


class MetricsCollector:
    """Tracks latency, pipeline skip rates, router usage, and LLM cost savings."""

    def __init__(self, cost_per_full_pipeline_usd: float = 0.05):
        self.cost_per_full_pipeline_usd = cost_per_full_pipeline_usd
        self._lock = threading.Lock()
        self.total_decisions: int = 0
        self.pipelines_requested: int = 0
        self.pipelines_skipped: int = 0
        self.human_escalations: int = 0
        self.trades_rejected: int = 0
        self.trades_executed: int = 0
        self.decisions_by_action: Dict[str, int] = {}
        self.decisions_by_gate: Dict[str, int] = {}
        self.router_usage: Dict[str, int] = {}
        self.latencies_by_gate: Dict[str, List[float]] = {}

    def record_gate_result(self, result: GateResult) -> None:
        """Update metrics with a gate result."""
        with self._lock:
            self.total_decisions += 1
            
            # Action counts
            self.decisions_by_action[result.decision] = (
                self.decisions_by_action.get(result.decision, 0) + 1
            )
            
            # Gate counts
            self.decisions_by_gate[result.gate_name] = (
                self.decisions_by_gate.get(result.gate_name, 0) + 1
            )
            
            # Router usage
            self.router_usage[result.router_used] = (
                self.router_usage.get(result.router_used, 0) + 1
            )
            
            # Latency tracking
            if result.gate_name not in self.latencies_by_gate:
                self.latencies_by_gate[result.gate_name] = []
            self.latencies_by_gate[result.gate_name].append(result.latency_ms)

            # Specific status metrics
            if result.decision == "escalate":
                self.human_escalations += 1
            elif result.decision == "reject":
                self.trades_rejected += 1

    def record_pipeline_run(self, was_skipped: bool, was_executed: bool = False) -> None:
        """Record whether a full multi-agent debate pipeline was skipped or run."""
        with self._lock:
            self.pipelines_requested += 1
            if was_skipped:
                self.pipelines_skipped += 1
            if was_executed:
                self.trades_executed += 1

    def get_summary(self) -> Dict[str, Any]:
        """Compute aggregated metrics summary."""
        with self._lock:
            skip_rate = (
                (self.pipelines_skipped / self.pipelines_requested)
                if self.pipelines_requested > 0
                else 0.0
            )
            escalation_rate = (
                (self.human_escalations / self.total_decisions)
                if self.total_decisions > 0
                else 0.0
            )
            cost_saved = self.pipelines_skipped * self.cost_per_full_pipeline_usd

            avg_latencies = {}
            for gate, times in self.latencies_by_gate.items():
                avg_latencies[gate] = (
                    round(sum(times) / len(times), 2) if times else 0.0
                )

            all_times = [t for times in self.latencies_by_gate.values() for t in times]
            overall_avg_latency = (
                round(sum(all_times) / len(all_times), 2) if all_times else 0.0
            )

            return {
                "total_decisions": self.total_decisions,
                "pipelines_requested": self.pipelines_requested,
                "pipelines_skipped": self.pipelines_skipped,
                "pipeline_skip_rate_pct": round(skip_rate * 100.0, 1),
                "cost_saved_usd": round(cost_saved, 3),
                "human_escalations": self.human_escalations,
                "escalation_rate_pct": round(escalation_rate * 100.0, 1),
                "trades_rejected": self.trades_rejected,
                "trades_executed": self.trades_executed,
                "decisions_by_action": dict(self.decisions_by_action),
                "router_usage": dict(self.router_usage),
                "avg_gate_latency_ms": avg_latencies,
                "overall_avg_latency_ms": overall_avg_latency,
            }
