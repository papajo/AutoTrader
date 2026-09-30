"""SEC EDGAR 8-K item 2.02 earnings release parser."""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger("Bot.PEADParser")


@dataclass
class EarningsEvent:
    """An earnings release event from an SEC 8-K item 2.02 filing."""
    ticker: str
    cik: str
    filing_datetime: datetime
    release_timing: str  # 'pre_market', 'intraday', 'after_hours'
    first_tradable_date: date
    reported_eps: Optional[float] = None
    consensus_eps: Optional[float] = None


class SEC8KParser:
    """Parses SEC EDGAR 8-K filings for item 2.02 (Results of Operations and Financial Condition)."""

    @staticmethod
    def classify_release_timing(dt: datetime) -> Tuple[str, date]:
        """Classify filing as pre-market, intraday, or after-hours and compute first tradable date."""
        filing_time = dt.time()
        filing_date = dt.date()

        if filing_time < time(9, 30):
            # Pre-market: Tradable at today's 09:30 open
            return "pre_market", filing_date
        elif filing_time >= time(16, 0):
            # After-hours: Tradable at next business day open
            next_bday = (pd.Timestamp(filing_date) + pd.offsets.BDay(1)).date()
            return "after_hours", next_bday
        else:
            # Intraday: Conservatively trade at next business day open to avoid intraday noise
            next_bday = (pd.Timestamp(filing_date) + pd.offsets.BDay(1)).date()
            return "intraday", next_bday

    @staticmethod
    def generate_synthetic_earnings_events(
        tickers: Optional[List[str]] = None,
        start_year: int = 2019,
        end_year: int = 2026,
        seed: int = 42,
    ) -> List[EarningsEvent]:
        """Generate quarterly earnings release events for 40 mega-cap stocks."""
        rng = np.random.default_rng(seed)
        tickers = tickers or [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK_B", "JPM", "V",
            "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV", "MRK", "NFLX",
            "AMD", "CRM", "BAC", "ADBE", "CVX", "WMT", "KO", "PEP", "TMO", "CSCO",
            "LIN", "ACN", "MCD", "DIS", "ABT", "INTC", "INTU", "VZ", "CMCSA", "QCOM"
        ]

        events = []
        quarter_months = [1, 4, 7, 10]

        for ticker in tickers:
            cik = str(hash(ticker) % 1_000_000).zfill(10)
            for year in range(start_year, end_year):
                for month in quarter_months:
                    # Earnings typically released mid-month
                    day = int(rng.integers(15, 28))
                    hour = int(rng.choice([8, 16, 17]))  # 8am pre-market, or 4/5pm after-hours
                    minute = int(rng.integers(0, 59))
                    dt = datetime(year, month, day, hour, minute)
                    timing, first_bday = SEC8KParser.classify_release_timing(dt)

                    events.append(EarningsEvent(
                        ticker=ticker,
                        cik=cik,
                        filing_datetime=dt,
                        release_timing=timing,
                        first_tradable_date=first_bday,
                    ))

        events.sort(key=lambda e: e.filing_datetime)
        return events
