"""Stateless policy engine mapping Laya & JEV answers to multi-asset trading actions."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from tradingagents.laya_integration.config import LayaConfig
from tradingagents.laya_integration.schemas import (
    AssetClass,
    MarketRegimeQuestions,
    NewsRiskQuestions,
    ThesisQualityQuestions,
    RiskComplianceQuestions,
    StockDetails,
    BondDetails,
    OptionDetails,
    CommodityDetails,
    ETFDetails,
    MutualFundDetails,
    ForexDetails,
    ProposedTrade,
)


def trading_gates_policy(
    answers: Any,
    config: LayaConfig,
    asset_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure, stateless function mapping Laya/JEV answers and thresholds to actions.

    Supported Actions:
        - "proceed": Continue to next pipeline stage or execute
        - "skip": Fast-path skip expensive multi-agent LLM analysis
        - "hedge": Flatten or hedge current exposure
        - "escalate": Escalate to human supervisor
        - "reduce": Reduce proposed position size (e.g. 50%)
        - "reject": Immediately reject trade due to risk/policy breach

    Returns:
        Dict with:
            - decision: str
            - reasons: List[str]
            - execution_action: Optional[str]
    """
    reasons: List[str] = []

    # -----------------------------------------------------------------------
    # Gate 1: Market Regime Policy
    # -----------------------------------------------------------------------
    if isinstance(answers, MarketRegimeQuestions):
        regime = answers.market_regime
        vol = answers.volatility_level

        if regime == "crisis" and config.thresholds.regime_skip_on_crisis:
            reasons.append(f"Market regime is CRISIS (vol={vol:.2f}); skipping expensive LLM debate.")
            return {
                "decision": "skip",
                "execution_action": "flat_or_hedge",
                "reasons": reasons,
            }

        if regime == "choppy" and config.thresholds.regime_skip_on_choppy:
            reasons.append(f"Market regime is CHOPPY (vol={vol:.2f}); skipping analysis to prevent over-trading.")
            return {
                "decision": "skip",
                "execution_action": "hold",
                "reasons": reasons,
            }

        if vol >= config.thresholds.volatility_macro_only:
            reasons.append(f"High volatility ({vol:.2f} >= {config.thresholds.volatility_macro_only:.2f}); route to macro node only.")
            return {
                "decision": "proceed",
                "execution_action": "run_macro_only",
                "reasons": reasons,
            }

        reasons.append(f"Market regime {regime} with normal volatility ({vol:.2f}); proceeding with full analysis.")
        return {
            "decision": "proceed",
            "execution_action": "continue_to_analysts",
            "reasons": reasons,
        }

    # -----------------------------------------------------------------------
    # Gate 2: News Risk Policy
    # -----------------------------------------------------------------------
    elif isinstance(answers, NewsRiskQuestions):
        event = answers.event_type
        macro_impact = answers.macro_impact
        signal_q = answers.signal_quality

        if signal_q < config.thresholds.news_signal_quality_min:
            reasons.append(
                f"Signal quality ({signal_q:.2f}) below minimum threshold "
                f"({config.thresholds.news_signal_quality_min:.2f}); skipping ticker today."
            )
            return {
                "decision": "skip",
                "execution_action": "skip_ticker_today",
                "reasons": reasons,
            }

        if macro_impact == "high" and signal_q >= config.thresholds.news_risk_macro_only:
            reasons.append(
                f"High macro impact ({event}) with high signal quality ({signal_q:.2f}); "
                "routing directly to macro specialist."
            )
            return {
                "decision": "proceed",
                "execution_action": "run_macro_only",
                "reasons": reasons,
            }

        reasons.append(f"News event ({event}) within normal bounds (signal_q={signal_q:.2f}).")
        return {
            "decision": "proceed",
            "execution_action": "continue_to_pipeline",
            "reasons": reasons,
        }

    # -----------------------------------------------------------------------
    # Gate 3: Thesis Quality Policy
    # -----------------------------------------------------------------------
    elif isinstance(answers, ThesisQualityQuestions):
        agreement = answers.analyst_agreement
        conviction = answers.conviction_level
        actionable = answers.thesis_actionable
        severity = answers.disagreement_severity

        if agreement < config.thresholds.analyst_agreement_escalate:
            reasons.append(
                f"Analyst agreement ({agreement:.2f}) below escalation threshold "
                f"({config.thresholds.analyst_agreement_escalate:.2f}); escalating to human supervisor."
            )
            return {
                "decision": "escalate",
                "execution_action": "escalate_to_human",
                "reasons": reasons,
            }

        if conviction < config.thresholds.thesis_conviction_min and severity == "severe":
            reasons.append(
                f"Low conviction ({conviction:.2f}) combined with severe analyst disagreement; "
                "escalating to human."
            )
            return {
                "decision": "escalate",
                "execution_action": "escalate_to_human",
                "reasons": reasons,
            }

        if actionable < config.thresholds.thesis_actionable_min:
            reasons.append(
                f"Thesis actionability ({actionable:.2f}) below threshold "
                f"({config.thresholds.thesis_actionable_min:.2f}); reducing trade size by 50%."
            )
            return {
                "decision": "reduce",
                "execution_action": "reduce_size_by_50_pct",
                "reasons": reasons,
            }

        reasons.append(f"High quality thesis approved: agreement={agreement:.2f}, conviction={conviction:.2f}.")
        return {
            "decision": "proceed",
            "execution_action": "continue_to_trader",
            "reasons": reasons,
        }

    # -----------------------------------------------------------------------
    # Gate 4: Multi-Asset Risk Compliance Policy
    # -----------------------------------------------------------------------
    elif isinstance(answers, RiskComplianceQuestions):
        v_thresh = config.thresholds.violation_threshold

        # 1. Core Portfolio Risk Checks
        if answers.violates_position_limit > v_thresh:
            reasons.append(f"Breached position limit score ({answers.violates_position_limit:.2f} > {v_thresh:.2f}).")
        if answers.violates_max_loss > v_thresh:
            reasons.append(f"Breached max daily loss limit score ({answers.violates_max_loss:.2f} > {v_thresh:.2f}).")
        if answers.violates_concentration > v_thresh:
            reasons.append(f"Breached portfolio concentration score ({answers.violates_concentration:.2f} > {v_thresh:.2f}).")
        if answers.violates_asset_specific_limit > v_thresh:
            reasons.append(f"Breached asset-specific constraint score ({answers.violates_asset_specific_limit:.2f} > {v_thresh:.2f}).")

        # 2. Contextual Multi-Asset Constraint Checks
        if asset_context:
            _check_asset_invariants(asset_context, config, reasons)

        if reasons:
            return {
                "decision": "reject",
                "execution_action": "reject_trade",
                "reasons": reasons,
            }

        # 3. Acceptable Risk / Reward Check
        if answers.acceptable_risk_reward < config.thresholds.acceptable_risk_reward_min:
            reasons.append(
                f"Risk/reward score ({answers.acceptable_risk_reward:.2f}) below minimum target "
                f"({config.thresholds.acceptable_risk_reward_min:.2f}); reducing size by {int(config.thresholds.reduce_size_factor * 100)}%."
            )
            return {
                "decision": "reduce",
                "execution_action": "reduce_size_by_50_pct",
                "reasons": reasons,
            }

        reasons.append("Trade satisfies all portfolio and asset-specific risk policies.")
        return {
            "decision": "proceed",
            "execution_action": "execute_order",
            "reasons": reasons,
        }

    # Default fallback
    return {
        "decision": "proceed",
        "execution_action": "continue",
        "reasons": ["Default policy evaluation."],
    }


def _check_asset_invariants(
    ctx: Dict[str, Any],
    config: LayaConfig,
    reasons: List[str],
) -> None:
    """Evaluate specific multi-asset constraints across Stocks, Bonds, Options, Commodities, ETFs, Mutual Funds, Forex."""
    asset_class = ctx.get("asset_class")
    details = ctx.get("details", {})
    if isinstance(details, dict):
        pass
    elif hasattr(details, "model_dump"):
        details = details.model_dump()
    else:
        details = {}

    # Stock / Equity Checks
    if asset_class == AssetClass.STOCK or asset_class == "stock":
        beta = details.get("beta", 1.0)
        if beta > config.stock_risk.max_beta:
            reasons.append(f"Stock beta {beta:.2f} exceeds allowable max {config.stock_risk.max_beta:.2f}.")
        mcap = details.get("market_cap")
        if mcap is not None and mcap < config.stock_risk.min_market_cap_usd:
            reasons.append(f"Market cap ${mcap:,.0f} below minimum ${config.stock_risk.min_market_cap_usd:,.0f}.")

    # Bond / Fixed Income Checks
    elif asset_class == AssetClass.BOND or asset_class == "bond":
        duration = details.get("duration", 0.0)
        if duration > config.bond_risk.max_duration_years:
            reasons.append(f"Bond duration {duration:.1f}y exceeds limit {config.bond_risk.max_duration_years:.1f}y.")
        rating = str(details.get("credit_rating", "AAA")).upper()
        if rating in ("CCC", "CC", "C", "D", "DEFAULT"):
            reasons.append(f"Credit rating {rating} falls below investment-grade floor ({config.bond_risk.min_credit_rating}).")

    # Option Derivatives Checks
    elif asset_class == AssetClass.OPTION or asset_class == "option":
        dte = details.get("expiration_days", 30)
        if dte < config.option_risk.min_days_to_expiration:
            reasons.append(f"Option expiration ({dte} DTE) too close to expiry (< {config.option_risk.min_days_to_expiration} days).")
        delta = abs(details.get("delta", 0.0))
        if delta > config.option_risk.max_portfolio_delta:
            reasons.append(f"Option delta ({delta:.2f}) exceeds single-contract limit ({config.option_risk.max_portfolio_delta:.2f}).")
        vega = abs(details.get("vega", 0.0))
        if vega > config.option_risk.max_portfolio_vega:
            reasons.append(f"Option vega ({vega:.1f}) exceeds vega limit ({config.option_risk.max_portfolio_vega:.1f}).")

    # Commodity Futures Checks
    elif asset_class == AssetClass.COMMODITY or asset_class == "commodity":
        delivery = details.get("delivery_settlement", "financial")
        curve = details.get("curve_state", "flat")
        storage_rate = details.get("storage_rate", 0.0)
        if config.commodity_risk.prohibit_physical_delivery and delivery == "physical":
            reasons.append("Physical delivery contracts prohibited by automated trading risk policy.")
        if curve == "contango" and storage_rate > config.commodity_risk.max_contango_roll_pct:
            reasons.append(f"Excessive contango roll drag ({storage_rate:.2%}) exceeds limit ({config.commodity_risk.max_contango_roll_pct:.2%}).")

    # ETF Checks
    elif asset_class == AssetClass.ETF or asset_class == "etf":
        te = details.get("tracking_error", 0.0)
        if te > config.etf_risk.max_tracking_error:
            reasons.append(f"ETF tracking error ({te:.3f}) exceeds threshold ({config.etf_risk.max_tracking_error:.3f}).")
        lev = abs(details.get("leverage_factor", 1.0))
        if lev > config.etf_risk.max_leverage_multiplier:
            reasons.append(f"ETF leverage {lev}x exceeds max limit {config.etf_risk.max_leverage_multiplier}x.")

    # Mutual Fund Checks
    elif asset_class == AssetClass.MUTUAL_FUND or asset_class == "mutual_fund":
        er = details.get("expense_ratio", 0.005)
        if er > config.mutual_fund_risk.max_expense_ratio:
            reasons.append(f"Mutual fund expense ratio ({er:.2%}) exceeds cap ({config.mutual_fund_risk.max_expense_ratio:.2%}).")

    # Forex Checks
    elif asset_class == AssetClass.FOREX or asset_class == "forex":
        stop_pips = ctx.get("stop_loss_pips", details.get("spread_pips", 0.0) * 10)
        if stop_pips > config.forex_risk.max_pip_risk_per_trade:
            reasons.append(f"Forex stop loss distance ({stop_pips:.1f} pips) exceeds policy limit ({config.forex_risk.max_pip_risk_per_trade:.1f} pips).")
        lev = details.get("leverage", 1.0)
        if lev > config.forex_risk.max_leverage:
            reasons.append(f"Forex account leverage ({lev}x) exceeds regulatory limit ({config.forex_risk.max_leverage}x).")
