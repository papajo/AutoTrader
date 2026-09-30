"""Reports generator implementing Prompt 8."""

from bot.reports.viz_core import (
    render_svg_card,
    render_svg_equity_curve,
    render_svg_cost_waterfall,
    render_verdict_badge,
)
from bot.reports.build import ReportBuilder

__all__ = [
    "render_svg_card",
    "render_svg_equity_curve",
    "render_svg_cost_waterfall",
    "render_verdict_badge",
    "ReportBuilder",
]
