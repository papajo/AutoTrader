"""Unit tests for AuditLogger and MetricsCollector telemetry."""

import os
import tempfile
import pytest
from tradingagents.laya_integration.hooks import AuditLogger, MetricsCollector
from tradingagents.laya_integration.schemas import AssetClass, GateResult


def test_audit_logger_write_and_read():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        temp_log = tf.name

    try:
        logger = AuditLogger(log_path=temp_log)
        res = GateResult(
            gate_name="PreflightGate",
            decision="proceed",
            confidence=0.92,
            reasons=["All good"],
            laya_answers={"regime": "bullish"},
            latency_ms=1.5,
            router_used="laya",
            asset_class=AssetClass.STOCK,
        )

        entry = logger.log_decision("PreflightGate", "NVDA", "stock", res)
        assert entry["symbol"] == "NVDA"
        assert entry["decision"] == "proceed"

        logs = logger.read_logs()
        assert len(logs) == 1
        assert logs[0]["confidence"] == 0.92
        assert logs[0]["gate_name"] == "PreflightGate"
    finally:
        if os.path.exists(temp_log):
            os.remove(temp_log)


def test_metrics_collector_calculations():
    collector = MetricsCollector(cost_per_full_pipeline_usd=0.05)

    res_proceed = GateResult(
        gate_name="PreflightGate",
        decision="proceed",
        confidence=0.90,
        reasons=[],
        latency_ms=12.0,
        router_used="laya",
    )
    res_escalate = GateResult(
        gate_name="ThesisQualityGate",
        decision="escalate",
        confidence=0.85,
        reasons=[],
        latency_ms=15.0,
        router_used="laya",
    )

    collector.record_gate_result(res_proceed)
    collector.record_gate_result(res_escalate)

    # Record 4 pipeline runs: 1 skipped, 3 executed
    collector.record_pipeline_run(was_skipped=True)
    collector.record_pipeline_run(was_skipped=False, was_executed=True)
    collector.record_pipeline_run(was_skipped=False, was_executed=True)
    collector.record_pipeline_run(was_skipped=False, was_executed=True)

    summary = collector.get_summary()

    assert summary["total_decisions"] == 2
    assert summary["pipelines_requested"] == 4
    assert summary["pipelines_skipped"] == 1
    assert summary["pipeline_skip_rate_pct"] == 25.0
    assert summary["cost_saved_usd"] == 0.05
    assert summary["human_escalations"] == 1
    assert summary["trades_executed"] == 3
    assert "PreflightGate" in summary["avg_gate_latency_ms"]
