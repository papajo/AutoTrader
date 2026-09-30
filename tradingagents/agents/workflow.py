"""Complete Multi-Agent LangGraph-style workflow with Laya & JEV non-autoregressive control gates."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from tradingagents.agents.analysts import (
    FundamentalsAnalyst,
    TechnicalAnalyst,
    NewsSentimentAnalyst,
    MacroAnalyst,
    OptionsGreeksAnalyst,
)
from tradingagents.agents.trader import TraderAgent
from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.gates import LayaGates
from tradingagents.laya_integration.schemas import AssetClass, ProposedTrade

logger = logging.getLogger("TradingAgents.Workflow")


class LayaControlledTrading:
    """Multi-agent trading engine with 4 fast-path non-autoregressive decision checkpoints."""

    def __init__(
        self,
        config: Optional[LayaConfig] = None,
        gates: Optional[LayaGates] = None,
    ):
        self.config = config or LayaConfig()
        self.gates = gates or LayaGates(config=self.config)

        # Analyst agents
        self.fundamentals = FundamentalsAnalyst()
        self.technicals = TechnicalAnalyst()
        self.sentiment = NewsSentimentAnalyst()
        self.macro = MacroAnalyst()
        self.greeks = OptionsGreeksAnalyst()

        # Trader execution agent
        self.trader = TraderAgent()

    def run_pipeline(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the end-to-end trading decision graph.

        Graph Stages:
            1. Preflight Gate (Market Regime) -> ~33ms
               - If crisis/choppy -> skip expensive pipeline, save cost/time.
            2. News Risk Gate -> ~33ms
               - If noise -> skip ticker today.
               - If high macro impact -> run macro analyst only.
            3. Analyst Debate (LLM Multi-Agent)
               - Fundamentals, Technicals, Sentiment, Macro, Greeks
            4. Thesis Quality Gate -> ~33ms
               - If low agreement / severe conflict -> escalate to human.
            5. Trader drafts proposal
            6. Risk Compliance Gate -> ~33ms
               - Multi-asset policy verification (stocks, bonds, options, commodities, ETFs, mutual funds, forex).
        """
        symbol = str(state.get("symbol", state.get("ticker", "NVDA")))
        asset_class_str = str(state.get("asset_class", "stock")).lower()
        pipeline_result: Dict[str, Any] = {
            "symbol": symbol,
            "asset_class": asset_class_str,
            "gates_executed": [],
            "pipeline_skipped": False,
            "human_escalated": False,
            "trade_approved": False,
            "order": None,
            "final_action": None,
        }

        # -------------------------------------------------------------------
        # GATE 1: Market Regime Classifier (~33ms)
        # -------------------------------------------------------------------
        g1_res = self.gates.run_preflight(state)
        pipeline_result["gates_executed"].append(g1_res)

        if g1_res["decision"] == "skip":
            pipeline_result["pipeline_skipped"] = True
            pipeline_result["final_action"] = g1_res["execution_action"]
            pipeline_result["reasons"] = g1_res["reasons"]
            if self.gates.metrics_collector:
                self.gates.metrics_collector.record_pipeline_run(was_skipped=True)
            return pipeline_result

        # -------------------------------------------------------------------
        # GATE 2: News & Macro Risk Classifier (~33ms)
        # -------------------------------------------------------------------
        g2_res = self.gates.run_news_risk(state)
        pipeline_result["gates_executed"].append(g2_res)

        if g2_res["decision"] == "skip":
            pipeline_result["pipeline_skipped"] = True
            pipeline_result["final_action"] = g2_res["execution_action"]
            pipeline_result["reasons"] = g2_res["reasons"]
            if self.gates.metrics_collector:
                self.gates.metrics_collector.record_pipeline_run(was_skipped=True)
            return pipeline_result

        # -------------------------------------------------------------------
        # Multi-Agent Analyst Collaboration / Debate
        # -------------------------------------------------------------------
        analyst_reports: Dict[str, Any] = {}
        if g2_res.get("execution_action") == "run_macro_only" or g1_res.get("execution_action") == "run_macro_only":
            logger.info("Fast routing: Running Macro specialist node only.")
            analyst_reports["macro"] = self.macro.analyze(state)
        else:
            # Full analyst team
            analyst_reports["fundamentals"] = self.fundamentals.analyze(state)
            analyst_reports["technicals"] = self.technicals.analyze(state)
            analyst_reports["sentiment"] = self.sentiment.analyze(state)
            analyst_reports["macro"] = self.macro.analyze(state)
            if asset_class_str == "option":
                analyst_reports["greeks"] = self.greeks.analyze(state)

        pipeline_result["analyst_reports"] = analyst_reports

        # Compute consensus agreement
        directions = [rep["direction"] for rep in analyst_reports.values()]
        agreement_score = (
            max(directions.count("buy"), directions.count("sell"), directions.count("hold"))
            / max(1, len(directions))
        )
        avg_conviction = sum(rep["conviction"] for rep in analyst_reports.values()) / max(1, len(directions))

        # Update state for Gate 3
        state["analyst_reports"] = analyst_reports
        state["analyst_agreement"] = agreement_score
        state["conviction_level"] = avg_conviction
        state["thesis_actionable"] = 0.85 if agreement_score >= 0.6 else 0.50

        # -------------------------------------------------------------------
        # GATE 3: Thesis Quality Scorer (~33ms)
        # -------------------------------------------------------------------
        g3_res = self.gates.run_thesis_quality(state)
        pipeline_result["gates_executed"].append(g3_res)

        if g3_res["decision"] == "escalate":
            pipeline_result["human_escalated"] = True
            pipeline_result["final_action"] = "escalate_to_human"
            pipeline_result["reasons"] = g3_res["reasons"]
            if self.gates.metrics_collector:
                self.gates.metrics_collector.record_pipeline_run(was_skipped=False, was_executed=False)
            return pipeline_result

        size_multiplier = 0.5 if g3_res["decision"] == "reduce" else 1.0

        # -------------------------------------------------------------------
        # Trader Agent: Draft Order Proposal
        # -------------------------------------------------------------------
        order_proposal: ProposedTrade = self.trader.draft_order(
            state,
            analyst_reports=analyst_reports,
            size_multiplier=size_multiplier,
        )
        pipeline_result["order"] = order_proposal.model_dump()
        state["proposed_trade"] = order_proposal.model_dump()

        # -------------------------------------------------------------------
        # GATE 4: Multi-Asset Risk Compliance Gate (~33ms)
        # -------------------------------------------------------------------
        g4_res = self.gates.run_risk_compliance(state)
        pipeline_result["gates_executed"].append(g4_res)

        if g4_res["decision"] == "reject":
            pipeline_result["trade_approved"] = False
            pipeline_result["final_action"] = "trade_rejected"
            pipeline_result["reasons"] = g4_res["reasons"]
            if self.gates.metrics_collector:
                self.gates.metrics_collector.record_pipeline_run(was_skipped=False, was_executed=False)
            return pipeline_result

        # Final sizing adjustment if risk/reward is borderline
        if g4_res["decision"] == "reduce":
            order_proposal.quantity = max(1.0, order_proposal.quantity * 0.5)
            pipeline_result["order"] = order_proposal.model_dump()

        pipeline_result["trade_approved"] = True
        pipeline_result["final_action"] = "execute_trade"
        pipeline_result["reasons"] = g4_res["reasons"]

        if self.gates.metrics_collector:
            self.gates.metrics_collector.record_pipeline_run(was_skipped=False, was_executed=True)

        return pipeline_result
