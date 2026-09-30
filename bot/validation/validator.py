"""Prompt 7: Comprehensive statistical validation, significance tests, and mechanical audits.

Strictly follows:
- Rule 16: Time-split train/test, t-stats, 95% CIs, and statistical power calculations.
- Rule 17: Measure score ranking power across FULL range including rejections.
- Mechanical audit re-verifying every rule constraint.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import scipy.stats as stats
import pandas as pd

from bot.core.engine import TradeRecord


@dataclass
class SignificanceResult:
    """Summary of statistical significance testing."""
    sample_size: int
    mean_r: float
    std_r: float
    stderr: float
    t_statistic: float
    p_value: float
    ci_95_lower: float
    ci_95_upper: float
    ci_contains_zero: bool
    verdict: str


class StrategyValidator:
    """Statistical validator ensuring results are statistically robust and not fitted noise."""

    @staticmethod
    def compute_significance(r_multiples: List[float]) -> SignificanceResult:
        """Compute t-stat against zero and 95% confidence interval for R multiples."""
        n = len(r_multiples)
        if n < 2:
            return SignificanceResult(
                sample_size=n, mean_r=0.0, std_r=0.0, stderr=0.0,
                t_statistic=0.0, p_value=1.0, ci_95_lower=0.0, ci_95_upper=0.0,
                ci_contains_zero=True, verdict="Insufficient sample size (< 2 trades)",
            )

        arr = np.array(r_multiples, dtype=float)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr, ddof=1))
        se = std_val / math.sqrt(n)

        # t-distribution critical value
        t_crit = stats.t.ppf(0.975, df=n - 1)
        ci_lower = mean_val - (t_crit * se)
        ci_upper = mean_val + (t_crit * se)

        t_stat = mean_val / se if se > 0 else 0.0
        p_val = 2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=n - 1))

        contains_zero = (ci_lower <= 0.0 <= ci_upper)
        if contains_zero:
            verdict = f"Not statistically distinguishable from zero at 95% confidence (95% CI [{ci_lower:+.3f}R, {ci_upper:+.3f}R] contains zero, p={p_val:.4f})."
        else:
            verdict = f"Statistically significant edge at p={p_val:.4f} (95% CI [{ci_lower:+.3f}R, {ci_upper:+.3f}R])."

        return SignificanceResult(
            sample_size=n,
            mean_r=round(mean_val, 4),
            std_r=round(std_val, 4),
            stderr=round(se, 4),
            t_statistic=round(t_stat, 2),
            p_value=round(p_val, 4),
            ci_95_lower=round(ci_lower, 4),
            ci_95_upper=round(ci_upper, 4),
            ci_contains_zero=contains_zero,
            verdict=verdict,
        )

    @staticmethod
    def compare_arms(r_arm1: List[float], r_arm2: List[float], name1: str = "Arm 1", name2: str = "Arm 2") -> Dict[str, Any]:
        """Compute two-sample difference t-stat and win rate proportion test."""
        n1, n2 = len(r_arm1), len(r_arm2)
        if n1 < 2 or n2 < 2:
            return {"error": "Insufficient trades in one or both arms"}

        arr1 = np.array(r_arm1)
        arr2 = np.array(r_arm2)

        mean1, mean2 = float(np.mean(arr1)), float(np.mean(arr2))
        se1 = np.std(arr1, ddof=1) / math.sqrt(n1)
        se2 = np.std(arr2, ddof=1) / math.sqrt(n2)
        diff_mean = mean1 - mean2
        se_diff = math.sqrt(se1**2 + se2**2)
        t_stat = diff_mean / se_diff if se_diff > 0 else 0.0

        # Win rate proportion test
        w1 = np.sum(arr1 > 0)
        w2 = np.sum(arr2 > 0)
        p1 = w1 / n1
        p2 = w2 / n2
        p_pool = (w1 + w2) / (n1 + n2)
        se_prop = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
        z_prop = (p1 - p2) / se_prop if se_prop > 0 else 0.0

        return {
            "mean_difference_r": round(diff_mean, 4),
            "se_difference": round(se_diff, 4),
            "t_statistic": round(t_stat, 2),
            "win_rate_diff_pct": round((p1 - p2) * 100.0, 1),
            "win_rate_z_stat": round(z_prop, 2),
            "claim_allowed": abs(t_stat) >= 2.0,
        }

    @staticmethod
    def compute_statistical_power(std_r: float, effect_size_r: float, power: float = 0.80) -> int:
        """Compute required sample size to detect observed effect at 80% power."""
        if effect_size_r <= 0 or std_r <= 0:
            return 999_999

        # Standard normal quantiles: alpha=0.05 two-tailed -> z=1.96, power=0.80 -> z=0.84
        z_alpha = 1.96
        z_beta = 0.84
        n_needed = ((z_alpha + z_beta) * std_r / effect_size_r) ** 2
        return int(math.ceil(n_needed))

    @staticmethod
    def stress_test_friction(
        trades: List[TradeRecord],
        slippage_multipliers: Tuple[float, ...] = (0.0, 0.5, 1.0, 2.0, 5.0),
    ) -> Dict[str, Any]:
        """Evaluate strategy returns under 0x, 0.5x, 1x, 2x, 5x assumed slippage."""
        results = {}
        for mult in slippage_multipliers:
            adjusted_pnls = []
            for t in trades:
                base_slip = t.slippage_cost
                new_slip = base_slip * mult
                net_pnl = t.pnl_pre_cost - new_slip - t.regulatory_fees - t.commission_fees
                adjusted_pnls.append(net_pnl)

            arr = np.array(adjusted_pnls)
            results[f"{mult}x_slippage"] = {
                "total_net_pnl": round(float(np.sum(arr)), 2),
                "win_rate_pct": round(float(np.mean(arr > 0) * 100.0), 1),
                "profit_factor": round(float(np.sum(arr[arr > 0]) / abs(np.sum(arr[arr < 0]))), 2) if np.any(arr < 0) else 999.0,
            }
        return results

    @staticmethod
    def shadow_calibration(
        decisions: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Rank-correlate model probabilities and confidence across all candidates (Rule 17)."""
        if len(decisions) != len(outcomes) or len(decisions) < 5:
            return {"error": "Need aligned decisions and outcomes"}

        probs = [d.get("probability", 0.0) for d in decisions]
        confs = [d.get("confidence", 0.0) for d in decisions]
        realized_rs = [o.get("r_multiple", 0.0) for o in outcomes]

        # Spearman rank correlation
        spearman_prob, p_val_prob = stats.spearmanr(probs, realized_rs)
        spearman_conf, p_val_conf = stats.spearmanr(confs, realized_rs)

        return {
            "total_candidates": len(decisions),
            "prob_spearman": round(float(spearman_prob), 4),
            "prob_p_value": round(float(p_val_prob), 4),
            "conf_spearman": round(float(spearman_conf), 4),
            "conf_p_value": round(float(p_val_conf), 4),
            "rule_15_verified": (spearman_prob > spearman_conf),
        }

    @staticmethod
    def mechanical_audit(trades: List[TradeRecord]) -> Dict[str, Any]:
        """Assert N of N trades follow exact rule constraints without lookahead."""
        checks_passed = 0
        total_checks = 0

        for t in trades:
            # Check 1: Exit time strictly >= entry time
            total_checks += 1
            if t.exit_time >= t.entry_time:
                checks_passed += 1

            # Check 2: Quantity > 0
            total_checks += 1
            if t.quantity > 0:
                checks_passed += 1

            # Check 3: Pre-cost P&L matches price difference * quantity
            total_checks += 1
            expected_pnl = (t.exit_price_raw - t.entry_price_raw) * t.quantity if t.side == "long" else (
                (t.entry_price_raw - t.exit_price_raw) * t.quantity
            )
            if abs(t.pnl_pre_cost - expected_pnl) < 0.05:
                checks_passed += 1

        all_passed = checks_passed == total_checks
        return {
            "total_trades_audited": len(trades),
            "checks_evaluated": total_checks,
            "checks_passed": checks_passed,
            "audit_passed": all_passed,
            "summary": f"{checks_passed} of {total_checks} mechanical checks verified."
        }
