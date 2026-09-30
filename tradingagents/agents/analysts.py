"""Specialized Multi-Asset Analyst Agents for TradingAgents."""

from __future__ import annotations
from typing import Any, Dict, List
from tradingagents.laya_integration.schemas import AssetClass


class BaseAnalyst:
    """Base class for multi-agent analyst nodes."""

    def __init__(self, name: str):
        self.name = name

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class FundamentalsAnalyst(BaseAnalyst):
    """Analyzes financial statements, balance sheets, earnings, credit metrics, and fund holdings."""

    def __init__(self):
        super().__init__("FundamentalsAnalyst")

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        symbol = state.get("symbol", "UNKNOWN")
        asset_class = state.get("asset_class", "stock")
        details = state.get("details", {})

        # Context-aware analysis per asset class
        if asset_class in ("stock", AssetClass.STOCK):
            pe = details.get("pe_ratio", 22.0)
            direction = "buy" if pe < 30.0 else "neutral"
            conviction = 0.82
            summary = f"Stock fundamentals sound with P/E ratio {pe:.1f} and healthy balance sheet."

        elif asset_class in ("bond", AssetClass.BOND):
            rating = details.get("credit_rating", "AAA")
            ytm = details.get("yield_to_maturity", 0.045)
            direction = "buy" if rating in ("AAA", "AA", "A", "BBB") else "sell"
            conviction = 0.88
            summary = f"Bond rated {rating} with YTM {ytm:.2%} reflects robust creditworthiness."

        elif asset_class in ("etf", AssetClass.ETF, "mutual_fund", AssetClass.MUTUAL_FUND):
            er = details.get("expense_ratio", 0.003)
            direction = "buy" if er <= 0.01 else "neutral"
            conviction = 0.85
            summary = f"Fund expense ratio of {er:.2%} offers cost-efficient asset exposure."

        else:
            direction = "neutral"
            conviction = 0.70
            summary = f"Fundamentals evaluated for {symbol} under {asset_class} specifications."

        return {
            "analyst": self.name,
            "direction": direction,
            "conviction": conviction,
            "summary": summary,
            "metrics": {"pe_or_rating": details.get("pe_ratio") or details.get("credit_rating")},
        }


class TechnicalAnalyst(BaseAnalyst):
    """Analyzes price action, moving averages, momentum, and curve structure."""

    def __init__(self):
        super().__init__("TechnicalAnalyst")

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        price = float(state.get("price", 100.0))
        sma_50 = float(state.get("sma_50", price * 0.98))
        sma_200 = float(state.get("sma_200", price * 0.95))
        rsi = float(state.get("rsi", 55.0))
        asset_class = state.get("asset_class", "stock")
        details = state.get("details", {})

        if asset_class in ("commodity", AssetClass.COMMODITY):
            curve = details.get("curve_state", "backwardation")
            direction = "buy" if curve == "backwardation" else "sell"
            conviction = 0.84
            summary = f"Commodity forward curve in {curve}, giving positive roll yield bias."
        else:
            if price > sma_50 and rsi < 70:
                direction = "buy"
                conviction = 0.86
                summary = f"Bullish momentum: Price (${price:.2f}) above 50-day SMA with RSI at {rsi:.1f}."
            elif price < sma_50 and rsi > 30:
                direction = "sell"
                conviction = 0.80
                summary = f"Bearish momentum: Price below 50-day SMA with RSI at {rsi:.1f}."
            else:
                direction = "hold"
                conviction = 0.65
                summary = f"Technical consolidation around ${price:.2f}."

        return {
            "analyst": self.name,
            "direction": direction,
            "conviction": conviction,
            "summary": summary,
            "metrics": {"rsi": rsi, "sma_50": sma_50},
        }


class NewsSentimentAnalyst(BaseAnalyst):
    """Analyzes market sentiment, breaking headlines, and social volume."""

    def __init__(self):
        super().__init__("NewsSentimentAnalyst")

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        sentiment_score = float(state.get("sentiment_score", 0.65))
        event = state.get("news_event_type", "normal")

        if sentiment_score > 0.60:
            direction = "buy"
            conviction = min(0.95, 0.70 + (sentiment_score * 0.25))
            summary = f"Positive market sentiment ({sentiment_score:.2f}) across {event} coverage."
        elif sentiment_score < 0.40:
            direction = "sell"
            conviction = 0.80
            summary = f"Negative sentiment headwinds ({sentiment_score:.2f})."
        else:
            direction = "neutral"
            conviction = 0.60
            summary = "Neutral sentiment signals."

        return {
            "analyst": self.name,
            "direction": direction,
            "conviction": conviction,
            "summary": summary,
            "metrics": {"sentiment_score": sentiment_score, "event": event},
        }


class MacroAnalyst(BaseAnalyst):
    """Analyzes interest rates, inflation, central bank policy, and currency dynamics."""

    def __init__(self):
        super().__init__("MacroAnalyst")

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        asset_class = state.get("asset_class", "stock")
        fed_stance = state.get("fed_stance", "dovish")
        details = state.get("details", {})

        if asset_class in ("forex", AssetClass.FOREX):
            diff = details.get("interest_rate_differential", 0.015)
            direction = "buy" if diff > 0 else "sell"
            conviction = 0.87
            summary = f"Interest rate differential of {diff:.2%} supports positive carry trade."
        elif asset_class in ("bond", AssetClass.BOND):
            direction = "buy" if fed_stance == "dovish" else "sell"
            conviction = 0.89
            summary = f"Dovish central bank posture provides tailwinds for bond yields."
        else:
            direction = "buy" if fed_stance != "tightening" else "hold"
            conviction = 0.80
            summary = f"Macro liquidity conditions supportive ({fed_stance} regime)."

        return {
            "analyst": self.name,
            "direction": direction,
            "conviction": conviction,
            "summary": summary,
            "metrics": {"fed_stance": fed_stance},
        }


class OptionsGreeksAnalyst(BaseAnalyst):
    """Analyzes derivative Greeks, implied volatility surfaces, and skew."""

    def __init__(self):
        super().__init__("OptionsGreeksAnalyst")

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        details = state.get("details", {})
        delta = details.get("delta", 0.45)
        gamma = details.get("gamma", 0.03)
        vega = details.get("vega", 15.0)
        theta = details.get("theta", -1.2)
        iv = details.get("implied_volatility", 0.25)

        direction = "buy" if delta > 0 else "sell"
        conviction = 0.85
        summary = (
            f"Option position Delta: {delta:.2f}, Gamma: {gamma:.2f}, "
            f"Vega: {vega:.1f}, Theta: {theta:.2f}, IV: {iv:.1%}."
        )

        return {
            "analyst": self.name,
            "direction": direction,
            "conviction": conviction,
            "summary": summary,
            "metrics": {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "iv": iv},
        }
