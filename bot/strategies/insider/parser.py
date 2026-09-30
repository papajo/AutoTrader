"""SEC Form 3/4/5 parser and insider transaction event builder."""

from __future__ import annotations
import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger("Bot.InsiderParser")


@dataclass
class InsiderPurchaseEvent:
    """An open-market purchase transaction by a corporate insider."""
    ticker: str
    filing_date: date
    transaction_date: date
    owner_name: str
    role: str  # 'officer', 'ceo_cfo_pres', 'director', 'ten_percent_owner'
    shares: float
    price_per_share: float
    total_value: float


class SECForm4Parser:
    """Parses SEC Form 4 insider transactions, filtering strictly for open-market purchases."""

    @staticmethod
    def parse_tsv_data(
        nonderiv_tsv: str,
        submission_tsv: Optional[str] = None,
        owner_tsv: Optional[str] = None,
    ) -> List[InsiderPurchaseEvent]:
        """Parse raw TSV contents from SEC Form 3/4/5 quarterly archives."""
        events: List[InsiderPurchaseEvent] = []
        
        # Read lines
        reader = csv.DictReader(io.StringIO(nonderiv_tsv), delimiter="\t")
        for row in reader:
            trans_code = row.get("TRANS_CODE", "").strip()
            acq_disp = row.get("TRANS_ACQUIRED_DISP_CD", "").strip()
            sec_title = row.get("SECURITY_TITLE", "").lower()

            # Filter for open-market purchases of common stock only
            if trans_code != "P" or acq_disp != "A":
                continue
            if not any(term in sec_title for term in ("common", "ordinary", "com", "class a")):
                continue

            try:
                price = float(row.get("TRANS_PRICE_PER_SHARE", 0.0))
                shares = float(row.get("TRANS_SHARES", 0.0))
            except (ValueError, TypeError):
                continue

            total_val = price * shares
            # Plausible trade bounds: $0.50 to $10,000 price, < $500M total
            if price < 0.50 or price > 10_000.0 or total_val <= 0 or total_val > 500_000_000.0:
                continue

            ticker = row.get("ISSUERTRADINGSYMBOL", "").strip().upper()
            if not ticker or ticker == "NONE":
                continue

            # Parse filing date
            filing_str = row.get("FILING_DATE", row.get("RPT_DATE", ""))
            try:
                filing_date = pd.to_datetime(filing_str).date()
            except Exception:
                continue

            role = row.get("RELATIONSHIP", "officer").lower()
            if any(t in role for t in ("ceo", "cfo", "president")):
                canonical_role = "ceo_cfo_pres"
            elif "director" in role:
                canonical_role = "director"
            elif "10%" in role or "ten" in role:
                canonical_role = "ten_percent_owner"
            else:
                canonical_role = "officer"

            events.append(InsiderPurchaseEvent(
                ticker=ticker,
                filing_date=filing_date,
                transaction_date=filing_date,
                owner_name=row.get("RPTOWNERNAME", "Insider"),
                role=canonical_role,
                shares=shares,
                price_per_share=price,
                total_value=total_val,
            ))

        return events

    @staticmethod
    def generate_synthetic_purchases(
        tickers: Optional[List[str]] = None,
        start_year: int = 2019,
        end_year: int = 2026,
        n_events: int = 250,
        seed: int = 42,
    ) -> List[InsiderPurchaseEvent]:
        """Generate statistically representative Form 4 purchases for offline backtesting."""
        rng = np.random.default_rng(seed)
        tickers = tickers or ["AAPL", "NVDA", "MSFT", "IWM", "TSLA", "AMD", "META", "AMZN", "GOOGL", "JPM", "XOM"]
        roles = ["officer", "ceo_cfo_pres", "director", "ten_percent_owner"]
        role_weights = [0.45, 0.25, 0.15, 0.15]

        dates = pd.bdate_range(f"{start_year}-01-01", f"{end_year}-08-01")
        events = []

        for _ in range(n_events):
            t = rng.choice(tickers)
            f_date = pd.to_datetime(rng.choice(dates)).date()
            role = rng.choice(roles, p=role_weights)
            val = float(rng.lognormal(mean=11.0, sigma=1.2))  # Typical $10k to $1M purchase
            val = min(val, 25_000_000.0)
            price = float(rng.uniform(15.0, 350.0))
            shares = val / price

            events.append(InsiderPurchaseEvent(
                ticker=t,
                filing_date=f_date,
                transaction_date=f_date,
                owner_name=f"{role.capitalize()} {rng.integers(100, 999)}",
                role=role,
                shares=round(shares, 2),
                price_per_share=round(price, 2),
                total_value=round(val, 2),
            ))

        events.sort(key=lambda e: e.filing_date)
        return events
