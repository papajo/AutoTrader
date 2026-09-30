"""LangChain Runnable & LangGraph-compatible gate nodes for Laya and JEV control layers."""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timezone

from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.hooks import AuditLogger, MetricsCollector
from tradingagents.laya_integration.policy import trading_gates_policy
from tradingagents.laya_integration.router import BaseRouter, UnifiedNonAutoregressiveRouter
from tradingagents.laya_integration.schemas import (
    AssetClass,
    GateResult,
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
)


class BaseGate:
    """Base class for all non-autoregressive gates, compliant with LangChain Runnable."""

    def __init__(
        self,
        name: str,
        config: LayaConfig,
        router: BaseRouter,
        schema_cls: Type[Any],
        audit_logger: Optional[AuditLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.name = name
        self.config = config
        self.router = router
        self.schema_cls = schema_cls
        self.audit_logger = audit_logger
        self.metrics_collector = metrics_collector

    def _is_enabled(self) -> bool:
        """Check if this gate is active in configuration."""
        if not self.config.enabled:
            return False
        if self.name == "PreflightGate":
            return self.config.preflight_regime_gate
        elif self.name == "NewsRiskGate":
            return self.config.news_risk_gate
        elif self.name == "ThesisQualityGate":
            return self.config.post_analyst_quality_gate
        elif self.name == "RiskComplianceGate":
            return self.config.risk_compliance_gate
        return True

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the gate evaluation on input state dictionary."""
        start_time = time.perf_counter()

        symbol = str(state.get("symbol", state.get("ticker", "UNKNOWN")))
        raw_asset_class = state.get("asset_class", "stock")
        try:
            asset_class = AssetClass(str(raw_asset_class).lower())
        except (ValueError, TypeError):
            asset_class = AssetClass.STOCK

        # If gate disabled, fast-pass immediately
        if not self._is_enabled():
            return {
                "decision": "proceed",
                "confidence": 1.0,
                "reasons": [f"{self.name} disabled in config; fast-passing."],
                "laya_answers": {},
                "execution_action": "continue",
                "router_used": "bypass",
                "latency_ms": 0.0,
                "gate_name": self.name,
                "asset_class": asset_class.value,
            }

        # Non-autoregressive inference via Laya or JEV
        answers, confidence, meta = self.router.predict(state, self.schema_cls)
        router_used = meta.get("router", "laya")

        # Context for multi-asset risk checks
        asset_context = {
            "symbol": symbol,
            "asset_class": asset_class,
            "details": state.get("details", state.get("asset_details", {})),
            "stop_loss_pips": state.get("stop_loss_pips"),
        }

        # Stateless policy evaluation
        policy_result = trading_gates_policy(answers, self.config, asset_context=asset_context)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Construct GateResult
        result = GateResult(
            gate_name=self.name,
            decision=policy_result["decision"],
            confidence=confidence,
            reasons=policy_result.get("reasons", []),
            laya_answers=answers.model_dump(),
            execution_action=policy_result.get("execution_action"),
            latency_ms=latency_ms,
            router_used=router_used,
            asset_class=asset_class,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Logging & Metrics hooks
        if self.audit_logger:
            self.audit_logger.log_decision(
                gate_name=self.name,
                symbol=symbol,
                asset_class=asset_class.value,
                result=result,
            )
        if self.metrics_collector:
            self.metrics_collector.record_gate_result(result)

        # Output TypedDict compatible format
        return {
            "decision": result.decision,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "laya_answers": result.laya_answers,
            "execution_action": result.execution_action,
            "router_used": result.router_used,
            "latency_ms": result.latency_ms,
            "gate_name": self.name,
            "asset_class": asset_class.value,
        }

    # LangChain Runnable interface compatibility
    def invoke(self, input: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """LangChain Runnable invoke."""
        return self.run(input)

    def batch(self, inputs: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """LangChain Runnable batch."""
        return [self.run(inp) for inp in inputs]

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Callable protocol."""
        return self.run(state)


class PreflightGate(BaseGate):
    """Gate 1: Market Regime Classifier (~33ms)."""

    def __init__(
        self,
        config: LayaConfig,
        router: BaseRouter,
        audit_logger: Optional[AuditLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        super().__init__(
            name="PreflightGate",
            config=config,
            router=router,
            schema_cls=MarketRegimeQuestions,
            audit_logger=audit_logger,
            metrics_collector=metrics_collector,
        )


class NewsRiskGate(BaseGate):
    """Gate 2: News Risk & Macro Impact Classifier (~33ms)."""

    def __init__(
        self,
        config: LayaConfig,
        router: BaseRouter,
        audit_logger: Optional[AuditLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        super().__init__(
            name="NewsRiskGate",
            config=config,
            router=router,
            schema_cls=NewsRiskQuestions,
            audit_logger=audit_logger,
            metrics_collector=metrics_collector,
        )


class ThesisQualityGate(BaseGate):
    """Gate 3: Post-Analyst Thesis Scorer (~33ms)."""

    def __init__(
        self,
        config: LayaConfig,
        router: BaseRouter,
        audit_logger: Optional[AuditLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        super().__init__(
            name="ThesisQualityGate",
            config=config,
            router=router,
            schema_cls=ThesisQualityQuestions,
            audit_logger=audit_logger,
            metrics_collector=metrics_collector,
        )


class RiskComplianceGate(BaseGate):
    """Gate 4: Multi-Asset Trade Risk & Compliance Gate (~33ms)."""

    def __init__(
        self,
        config: LayaConfig,
        router: BaseRouter,
        audit_logger: Optional[AuditLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        super().__init__(
            name="RiskComplianceGate",
            config=config,
            router=router,
            schema_cls=RiskComplianceQuestions,
            audit_logger=audit_logger,
            metrics_collector=metrics_collector,
        )


class LayaGates:
    """Master manager for Laya & JEV non-autoregressive gates."""

    def __init__(
        self,
        config: Optional[LayaConfig] = None,
        router: Optional[BaseRouter] = None,
    ):
        self.config = config or LayaConfig()
        self.router = router or UnifiedNonAutoregressiveRouter(self.config)
        self.audit_logger = AuditLogger(log_path=self.config.audit_log_path)
        self.metrics_collector = MetricsCollector() if self.config.enable_metrics else None

        # Instantiate 4 gates
        self.preflight = PreflightGate(
            config=self.config,
            router=self.router,
            audit_logger=self.audit_logger,
            metrics_collector=self.metrics_collector,
        )
        self.news_risk = NewsRiskGate(
            config=self.config,
            router=self.router,
            audit_logger=self.audit_logger,
            metrics_collector=self.metrics_collector,
        )
        self.thesis_quality = ThesisQualityGate(
            config=self.config,
            router=self.router,
            audit_logger=self.audit_logger,
            metrics_collector=self.metrics_collector,
        )
        self.risk_compliance = RiskComplianceGate(
            config=self.config,
            router=self.router,
            audit_logger=self.audit_logger,
            metrics_collector=self.metrics_collector,
        )

    def run_preflight(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run Gate 1."""
        return self.preflight.run(state)

    def run_news_risk(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run Gate 2."""
        return self.news_risk.run(state)

    def run_thesis_quality(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run Gate 3."""
        return self.thesis_quality.run(state)

    def run_risk_compliance(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run Gate 4."""
        return self.risk_compliance.run(state)

    def get_metrics(self) -> Dict[str, Any]:
        """Retrieve aggregated performance and savings metrics."""
        if self.metrics_collector:
            return self.metrics_collector.get_summary()
        return {}

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve latest audit records."""
        return self.audit_logger.read_logs(limit=limit)
