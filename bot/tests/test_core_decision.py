"""Unit tests for bot/core/decision.py."""

import os
import tempfile
from datetime import datetime
import pytest
from bot.core.contracts import Snapshot
from bot.core.decision import RuleDecider, GateDecider, JevDecider


@pytest.fixture
def sample_snapshot():
    return Snapshot(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 15, 10, 0),
        price=185.50,
        action="enter_long",
        features={"dist_ema50_atr": 0.5, "body_pct": 0.65},
        context=["Price is above 50 EMA", "Strong body"],
    )


def test_rule_decider(sample_snapshot):
    decider = RuleDecider()
    dec = decider.decide(sample_snapshot)
    assert dec.approved is True
    assert dec.chosen_action == "enter_long"


def test_gate_decider_veto(sample_snapshot):
    gated = GateDecider()
    # Add passing veto
    gated.add_veto(lambda s: (s.features["dist_ema50_atr"] < 0, "Counter-trend"))
    dec1 = gated.decide(sample_snapshot)
    assert dec1.approved is True

    # Add failing veto
    gated.add_veto(lambda s: (s.features["body_pct"] > 0.50, "Body too large"))
    dec2 = gated.decide(sample_snapshot)
    assert dec2.approved is False
    assert dec2.chosen_action == "wait"
    assert "Body too large" in dec2.reasons[0]


def test_jev_decider_sha_caching_and_logging(sample_snapshot):
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, "jev_cache")
        log_file = os.path.join(tmpdir, "decisions.jsonl")

        jev = JevDecider(
            cache_dir=cache_dir,
            log_file=log_file,
            probability_threshold=0.30,
        )

        # First call creates cache
        dec1 = jev.decide(sample_snapshot)
        assert dec1.decider_type == "jev"
        assert os.path.exists(log_file)
        assert len(os.listdir(cache_dir)) == 1

        # Second identical call reads from cache
        dec2 = jev.decide(sample_snapshot)
        assert dec1.probability == dec2.probability
        assert dec1.approved == dec2.approved
