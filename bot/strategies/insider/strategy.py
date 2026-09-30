"""Prompt 2: Corporate Insider Filings Strategy (SEC Form 3/4/5 open-market purchases).

Features:
- Event study measuring forward excess return at 5, 20, 60, 120 sessions.
- Mark-to-market portfolio book with K=10 slots, equal 1/K weighting, H=5 day hold.
- Regression against IWM benchmark reporting alpha, beta, and t(alpha).
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.data import StockDataClient
from bot.strategies.insider.parser import InsiderPurchaseEvent, SECForm4Parser


@dataclass
class Position:
    """An open portfolio slot."""
    ticker: str
    entry_date: date
    entry_price: float
    shares: float
    holding_days: int = 0


class InsiderTradingStrategy:
    """Corporate Insider Strategy: K=10 slots, 5-day hold, SEC Form 4 open-market purchases."""

    def __init__(
        self,
        k_slots: int = 10,
        holding_days: int = 5,
        min_purchase_value: float = 10_000.0,
        cost_bps: float = 30.0,  # 30 bps round-trip friction
        benchmark_symbol: str = "IWM",
    ):
        self.k_slots = k_slots
        self.holding_days = holding_days
        self.min_purchase_value = min_purchase_value
        self.cost_bps = cost_bps
        self.benchmark_symbol = benchmark_symbol

    def run_event_study(
        self,
        events: List[InsiderPurchaseEvent],
        price_data: Dict[str, pd.DataFrame],
        benchmark_df: pd.DataFrame,
        horizons: Tuple[int, ...] = (5, 20, 60, 120),
    ) -> Dict[str, Any]:
        """Compute forward excess return over benchmark at specified day horizons."""
        records = []

        # Prepare benchmark daily returns
        bm_daily = benchmark_df.resample("1D").agg({"open": "first", "close": "last"}).dropna()

        for ev in events:
            if ev.total_value < self.min_purchase_value:
                continue

            ticker = ev.ticker
            if ticker not in price_data or price_data[ticker].empty:
                continue

            df = price_data[ticker]
            daily_prices = df.resample("1D").agg({"open": "first", "close": "last"}).dropna()
            
            # Find next session after filing date
            forward_bars = daily_prices.loc[daily_prices.index.date > ev.filing_date]
            if len(forward_bars) < max(horizons):
                continue

            entry_open = forward_bars.iloc[0]["open"]
            entry_date = forward_bars.index[0].date()

            # Benchmark at entry
            bm_forward = bm_daily.loc[bm_daily.index.date >= entry_date]
            if len(bm_forward) < max(horizons):
                continue
            bm_entry_open = bm_forward.iloc[0]["open"]

            row = {
                "ticker": ticker,
                "filing_date": ev.filing_date,
                "role": ev.role,
                "total_value": ev.total_value,
            }

            for h in horizons:
                if len(forward_bars) > h:
                    exit_close = forward_bars.iloc[h - 1]["close"]
                    ret_stock = (exit_close - entry_open) / entry_open

                    bm_exit_close = bm_forward.iloc[h - 1]["close"]
                    ret_bm = (bm_exit_close - bm_entry_open) / bm_entry_open

                    excess = ret_stock - ret_bm
                    row[f"excess_{h}d"] = excess

            records.append(row)

        df_study = pd.DataFrame(records)
        summary = {}
        for h in horizons:
            col = f"excess_{h}d"
            if col in df_study.columns and not df_study[col].dropna().empty:
                vals = df_study[col].dropna().values
                mean_val = float(np.mean(vals))
                std_val = float(np.std(vals, ddof=1)) if len(vals) > 1 else 1.0
                t_stat = (mean_val / (std_val / math.sqrt(len(vals)))) if len(vals) > 1 else 0.0
                summary[f"{h}d"] = {
                    "n": len(vals),
                    "mean_pct": round(mean_val * 100.0, 2),
                    "t_stat": round(t_stat, 2),
                }

        return {"summary": summary, "events_analyzed": len(records)}

    def run_marked_to_market_book(
        self,
        events: List[InsiderPurchaseEvent],
        price_data: Dict[str, pd.DataFrame],
        benchmark_df: pd.DataFrame,
        initial_capital: float = 100_000.0,
    ) -> Dict[str, Any]:
        """Execute K=10 marked-to-market portfolio book with 5-day holds."""
        # Filter qualifying filings >= $10k
        qualifying = [e for e in events if e.total_value >= self.min_purchase_value]
        # Group by filing date
        events_by_date: Dict[date, List[InsiderPurchaseEvent]] = {}
        for e in qualifying:
            events_by_date.setdefault(e.filing_date, []).append(e)

        # Merge all trading dates
        all_dates = sorted(list(benchmark_df.resample("1D").first().dropna().index.date))

        capital = initial_capital
        cash = initial_capital
        open_positions: List[Position] = []
        equity_curve: List[Dict[str, Any]] = []

        daily_returns: List[float] = []
        bm_returns: List[float] = []

        bm_daily = benchmark_df.resample("1D").agg({"open": "first", "close": "last"}).dropna()

        for idx, current_date in enumerate(all_dates):
            # 1. Age positions and close any that reached holding_days (H=5)
            remaining_positions: List[Position] = []
            for pos in open_positions:
                pos.holding_days += 1
                if pos.holding_days >= self.holding_days:
                    # Close at today's open
                    df = price_data.get(pos.ticker)
                    if df is not None and not df.empty:
                        day_bar = df.loc[df.index.date == current_date]
                        exit_price = day_bar.iloc[0]["open"] if not day_bar.empty else pos.entry_price
                    else:
                        exit_price = pos.entry_price
                    
                    gross_proceeds = pos.shares * exit_price
                    cost = gross_proceeds * (self.cost_bps / 10000.0)
                    cash += (gross_proceeds - cost)
                else:
                    remaining_positions.append(pos)
            open_positions = remaining_positions

            # 2. Add new qualifying filings from previous day
            prev_date = all_dates[idx - 1] if idx > 0 else current_date
            todays_filings = events_by_date.get(prev_date, [])
            # Sort by total value descending (largest first)
            todays_filings.sort(key=lambda e: e.total_value, reverse=True)

            free_slots = self.k_slots - len(open_positions)
            slots_to_fill = min(free_slots, len(todays_filings))

            for i in range(slots_to_fill):
                event = todays_filings[i]
                df = price_data.get(event.ticker)
                if df is None or df.empty:
                    continue
                day_bar = df.loc[df.index.date == current_date]
                if day_bar.empty:
                    continue

                entry_price = day_bar.iloc[0]["open"]
                slot_budget = capital / self.k_slots
                if cash >= slot_budget and entry_price > 0:
                    shares = slot_budget / entry_price
                    cost = slot_budget * (self.cost_bps / 10000.0)
                    cash -= (slot_budget + cost)
                    open_positions.append(Position(
                        ticker=event.ticker,
                        entry_date=current_date,
                        entry_price=entry_price,
                        shares=shares,
                    ))

            # 3. Mark to market at close of session
            portfolio_val = cash
            for pos in open_positions:
                df = price_data.get(pos.ticker)
                if df is not None and not df.empty:
                    day_bar = df.loc[df.index.date == current_date]
                    close_p = day_bar.iloc[-1]["close"] if not day_bar.empty else pos.entry_price
                else:
                    close_p = pos.entry_price
                portfolio_val += pos.shares * close_p

            if equity_curve:
                prev_val = equity_curve[-1]["equity"]
                ret = (portfolio_val - prev_val) / prev_val
            else:
                ret = 0.0

            daily_returns.append(ret)
            capital = portfolio_val

            equity_curve.append({
                "date": current_date.isoformat(),
                "equity": round(portfolio_val, 2),
                "open_positions": len(open_positions),
            })

        # Calculate Alpha and Beta against benchmark
        arr_ret = np.array(daily_returns[1:])
        # Benchmark daily returns
        bm_closes = bm_daily["close"].values
        arr_bm = np.diff(bm_closes) / bm_closes[:-1]
        min_len = min(len(arr_ret), len(arr_bm))
        arr_ret = arr_ret[:min_len]
        arr_bm = arr_bm[:min_len]

        if min_len > 10 and np.var(arr_bm) > 0:
            cov = np.cov(arr_ret, arr_bm)[0, 1]
            var_bm = np.var(arr_bm)
            beta = float(cov / var_bm)
            alpha_daily = float(np.mean(arr_ret) - beta * np.mean(arr_bm))
            alpha_annual = float(alpha_daily * 252.0)
            residuals = arr_ret - (alpha_daily + beta * arr_bm)
            se_alpha = float(np.std(residuals) / math.sqrt(min_len) * math.sqrt(252.0))
            t_alpha = float(alpha_annual / se_alpha) if se_alpha > 0 else 0.0
        else:
            beta = 1.0
            alpha_annual = 0.0
            t_alpha = 0.0

        total_ret = (capital - initial_capital) / initial_capital
        cagr = ((capital / initial_capital) ** (252.0 / max(1, len(all_dates))) - 1.0) * 100.0

        return {
            "initial_capital": initial_capital,
            "final_equity": round(capital, 2),
            "total_return_pct": round(total_ret * 100.0, 2),
            "cagr_pct": round(cagr, 2),
            "beta": round(beta, 2),
            "alpha_annual_pct": round(alpha_annual * 100.0, 2),
            "t_alpha": round(t_alpha, 2),
            "benchmark": self.benchmark_symbol,
            "equity_curve": equity_curve,
        }
