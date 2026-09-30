"""Unit tests for validation engine (Prompt 7) and report builder (Prompt 8)."""

import os
import tempfile
import pytest
from bot.validation.validator import StrategyValidator
from bot.reports.build import ReportBuilder
from bot.reports.viz_core import render_svg_card, render_svg_equity_curve


def test_validator_significance_and_comparison():
    # 20 trades with positive mean
    r_multiples = [0.2, 0.4, -0.1, 0.5, 0.3, -0.2, 0.4, 0.6, -0.1, 0.2] * 2
    sig = StrategyValidator.compute_significance(r_multiples)
    assert sig.sample_size == 20
    assert sig.mean_r > 0
    assert not sig.ci_contains_zero

    # Compare two arms
    comp = StrategyValidator.compare_arms(r_multiples, [-0.1] * 20)
    assert comp["mean_difference_r"] > 0
    assert comp["claim_allowed"] is True


def test_validator_power_calculation():
    # Detect 0.10R effect with std 1.0 at 80% power
    n_needed = StrategyValidator.compute_statistical_power(std_r=1.0, effect_size_r=0.10)
    assert n_needed > 500  # Should need ~784 trades


def test_report_builder_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        builder = ReportBuilder(out_dir=tmpdir)
        builder.build_all_reports()

        generated_files = os.listdir(tmpdir)
        assert "index.html" in generated_files
        assert "orb.html" in generated_files
        assert "insider.html" in generated_files
        assert "earnings_drift.html" in generated_files
        assert "overnight_futures.html" in generated_files
        assert "news_scalp.html" in generated_files
        assert "lunar_gann.html" in generated_files
