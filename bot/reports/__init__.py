"""Reports generator implementing Prompt 8."""

from bot.reports.viz_core import (
    render_svg_card,
    render_svg_equity_curve,
    render_svg_cost_waterfall,
    render_verdict_badge,
)

__all__ = [
    "render_svg_card",
    "render_svg_equity_curve",
    "render_svg_cost_waterfall",
    "render_verdict_badge",
    "ReportBuilder",
]


def __getattr__(name: str):
    """Lazy import of ReportBuilder to avoid runpy RuntimeWarning when executing with -m."""
    if name == "ReportBuilder":
        from bot.reports.build import ReportBuilder
        return ReportBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
