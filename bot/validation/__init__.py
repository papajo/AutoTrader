"""Validation engine implementing Prompt 7."""

from bot.validation.validator import StrategyValidator, SignificanceResult

__all__ = [
    "StrategyValidator",
    "SignificanceResult",
    "run_orb_validation",
]


def __getattr__(name: str):
    """Lazy import of run_orb_validation to avoid runpy RuntimeWarning when executing with -m."""
    if name == "run_orb_validation":
        from bot.validation.run_validation import run_orb_validation
        return run_orb_validation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
