"""Validation CLI runner for Prompt 7."""

from __future__ import annotations
import argparse
import json
import logging
from typing import Any, Dict

from bot.strategies.orb import ORBStrategy
from bot.validation.validator import StrategyValidator

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Bot.ValidationRunner")


def run_orb_validation() -> Dict[str, Any]:
    """Run full statistical validation pass on Opening Range Breakout across all three arms."""
    logger.info("Running Prompt 7 Validation Pass on ORB Strategy (SPY)...")
    orb = ORBStrategy()
    results = orb.run_all_three_arms("SPY", start_date="2023-01-01", end_date="2026-08-01")

    rules_trades = results["rules"]["trades"]
    gated_trades = results["gated"]["trades"]
    jev_trades = results["jev"]["trades"]

    # 1. Significance for each arm
    sig_rules = StrategyValidator.compute_significance([t.r_multiple for t in rules_trades])
    sig_gated = StrategyValidator.compute_significance([t.r_multiple for t in gated_trades])
    sig_jev = StrategyValidator.compute_significance([t.r_multiple for t in jev_trades])

    # 2. Arm comparison: Jev vs Gated, Jev vs Rules
    comp_jev_gated = StrategyValidator.compare_arms(
        [t.r_multiple for t in jev_trades],
        [t.r_multiple for t in gated_trades],
        name1="Jev", name2="Gated",
    )

    # 3. Statistical power
    power_needed = StrategyValidator.compute_statistical_power(
        std_r=sig_jev.std_r if sig_jev.std_r > 0 else 1.0,
        effect_size_r=sig_jev.mean_r if sig_jev.mean_r > 0 else 0.10,
    )

    # 4. Mechanical audit
    audit = StrategyValidator.mechanical_audit(jev_trades)

    report = {
        "strategy": "Opening Range Breakout (ORB)",
        "significance": {
            "rules": sig_rules.__dict__,
            "gated": sig_gated.__dict__,
            "jev": sig_jev.__dict__,
        },
        "comparison_jev_vs_gated": comp_jev_gated,
        "sample_size_for_80pct_power": power_needed,
        "mechanical_audit": audit,
    }

    logger.info("\n" + "=" * 60)
    logger.info("📊 PROMPT 7 STATISTICAL VALIDATION REPORT")
    logger.info("=" * 60)
    logger.info(f"Rules Arm : {sig_rules.sample_size} trades | Mean R = {sig_rules.mean_r:+.4f} | t = {sig_rules.t_statistic} | {sig_rules.verdict}")
    logger.info(f"Gated Arm : {sig_gated.sample_size} trades | Mean R = {sig_gated.mean_r:+.4f} | t = {sig_gated.t_statistic} | {sig_gated.verdict}")
    logger.info(f"Jev Arm   : {sig_jev.sample_size} trades | Mean R = {sig_jev.mean_r:+.4f} | t = {sig_jev.t_statistic} | {sig_jev.verdict}")
    logger.info("-" * 60)
    logger.info(f"Jev vs Gated Difference : Mean ΔR = {comp_jev_gated.get('mean_difference_r'):+.4f} | t = {comp_jev_gated.get('t_statistic')}")
    logger.info(f"Trades Needed for 80% Power : {power_needed}")
    logger.info(f"Mechanical Audit : {audit['summary']}")
    logger.info("=" * 60 + "\n")

    return report


if __name__ == "__main__":
    run_orb_validation()
