"""Strategy-to-decider contract definitions.

Note: Named contracts.py (NOT types.py) to prevent shadowing Python's standard library.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

ActionType = Literal["enter_long", "enter_short", "wait", "exit"]


@dataclass
class Snapshot:
    """Carries the state of a single bar/candidate trade between strategy, gates, and model.

    Both numeric features and text context are built from the exact same row so neither
    layer gets an information advantage.
    """
    symbol: str
    timestamp: datetime
    price: float
    action: ActionType
    features: Dict[str, float] = field(default_factory=dict)
    context: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_state_text(self) -> str:
        """Render plain-English context lines into state string for the decision model."""
        header = f"Symbol: {self.symbol} | Timestamp: {self.timestamp.isoformat()} | Price: {self.price:.4f} | Proposed Action: {self.action}\n"
        body = "\n".join(f"- {line}" for line in self.context)
        return header + body


@dataclass
class Decision:
    """Output from a decision layer (RuleDecider, GateDecider, or JevDecider)."""
    approved: bool
    chosen_action: ActionType
    probability: float
    confidence: float
    reasons: List[str] = field(default_factory=list)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    decider_type: str = "rule"
