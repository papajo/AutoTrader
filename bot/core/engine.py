"""Portfolio execution engine strictly implementing Rules 1 through 11.

- Rule 1: No same-bar lookahead. Fill at bar close, stops checked from NEXT bar onward.
- Rule 2: Model friction per side (slippage in bps/ticks + SEC Section 31 + FINRA TAF on equity sales).
- Rule 3: Separate pre-cost and net P&L without double counting slippage.
- Rule 4: Target exits are resting limit orders (NO slippage); stops and time exits slip.
- Rule 5: Count ambiguous bars (both stop & target touched) -> resolve pessimistically as stop-first.
- Rule 6: Risk-based sizing with achieved risk reporting.
- Rule 7: Futures sized against margin not notional, handle < 1 contract.
- Rule 11: NumPy arrays in the per-bar loop (no slow DataFrame.loc).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
import numpy as np
import pandas as pd

from bot.core.contracts import ActionType, Snapshot


@dataclass
class Instrument:
    """Instrument specifications for equities and futures."""
    symbol: str
    asset_type: Literal["equity", "future"] = "equity"
    multiplier: float = 1.0
    tick_size: float = 0.01
    slippage_bps: float = 5.0  # For equities (basis points)
    slippage_ticks: float = 1.0  # For futures (ticks per side)
    commission_per_contract: float = 0.0  # Per contract per side for futures
    margin_requirement: float = 0.0  # Required initial margin per contract
    # Regulatory fees on equity sales
    sec_fee_rate: float = 0.0000278  # Section 31 fee on total sale value
    finra_taf_per_share: float = 0.000166  # FINRA TAF per share sold (max $8.30)
    finra_taf_cap: float = 8.30

    @classmethod
    def equity(cls, symbol: str, slippage_bps: float = 5.0) -> "Instrument":
        return cls(symbol=symbol, asset_type="equity", multiplier=1.0, tick_size=0.01, slippage_bps=slippage_bps)

    @classmethod
    def mes(cls) -> "Instrument":
        """Micro E-mini S&P 500."""
        return cls(symbol="MES", asset_type="future", multiplier=5.0, tick_size=0.25,
                   slippage_ticks=1.0, commission_per_contract=0.62, margin_requirement=1500.0)

    @classmethod
    def mnq(cls) -> "Instrument":
        """Micro E-mini Nasdaq-100."""
        return cls(symbol="MNQ", asset_type="future", multiplier=2.0, tick_size=0.25,
                   slippage_ticks=1.0, commission_per_contract=0.62, margin_requirement=2000.0)

    @classmethod
    def m2k(cls) -> "Instrument":
        """Micro E-mini Russell 2000."""
        return cls(symbol="M2K", asset_type="future", multiplier=10.0, tick_size=0.10,
                   slippage_ticks=1.0, commission_per_contract=0.62, margin_requirement=1000.0)

    @classmethod
    def mym(cls) -> "Instrument":
        """Micro E-mini Dow."""
        return cls(symbol="MYM", asset_type="future", multiplier=0.5, tick_size=1.0,
                   slippage_ticks=1.0, commission_per_contract=0.62, margin_requirement=1200.0)

    @classmethod
    def es(cls) -> "Instrument":
        """Full-size E-mini S&P 500."""
        return cls(symbol="ES", asset_type="future", multiplier=50.0, tick_size=0.25,
                   slippage_ticks=1.0, commission_per_contract=2.25, margin_requirement=15000.0)


@dataclass
class TradeRecord:
    """Record of an executed round-trip trade with full cost waterfall."""
    trade_id: int
    symbol: str
    side: Literal["long", "short"]
    entry_time: datetime
    exit_time: datetime
    entry_price_raw: float
    entry_price_slipped: float
    exit_price_raw: float
    exit_price_slipped: float
    quantity: float
    stop_price: float
    target_price: float
    exit_reason: Literal["target", "stop", "time_exit", "market_close"]
    pnl_pre_cost: float
    slippage_cost: float
    regulatory_fees: float
    commission_fees: float
    pnl_net: float
    r_multiple: float
    was_ambiguous_bar: bool = False
    holding_bars: int = 0
    arm: str = "rules"


class BacktestEngine:
    """Event-driven portfolio backtester enforcing Rules 1-11."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 0.01,  # 1% equity risk per trade
        max_notional_pct: float = 1.0,
        instruments: Optional[Dict[str, Instrument]] = None,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_notional_pct = max_notional_pct
        self.instruments = instruments or {}
        
        self.trades: List[TradeRecord] = []
        self.ambiguous_bars_count: int = 0
        self.total_candidates_evaluated: int = 0
        self.achieved_risks: List[float] = []

    def get_instrument(self, symbol: str) -> Instrument:
        if symbol not in self.instruments:
            # Default to equity
            self.instruments[symbol] = Instrument.equity(symbol)
        return self.instruments[symbol]

    def calculate_sizing(
        self,
        instrument: Instrument,
        entry_price: float,
        stop_price: float,
        equity: float,
    ) -> Tuple[float, float]:
        """Rule 6 & 7: Risk-based sizing with achieved risk reporting and futures margin handling."""
        risk_distance = abs(entry_price - stop_price)
        if risk_distance <= 0:
            return 0.0, 0.0

        target_risk_dollars = equity * self.risk_per_trade_pct

        if instrument.asset_type == "future":
            # Futures: Risk per contract = risk_distance * multiplier
            risk_per_contract = risk_distance * instrument.multiplier
            margin_req = max(1.0, instrument.margin_requirement)
            
            # Size against margin not notional (Rule 7)
            max_contracts_by_margin = equity / margin_req
            target_contracts = target_risk_dollars / risk_per_contract

            # Handle case where budget buys < 1 contract
            contracts = int(min(target_contracts, max_contracts_by_margin))
            if contracts < 1:
                # If risk budget buys less than 1 contract, allocate exactly 1 if margin permits
                if equity >= margin_req:
                    contracts = 1
                else:
                    return 0.0, 0.0

            achieved_risk_pct = (contracts * risk_per_contract) / equity
            return float(contracts), achieved_risk_pct

        else:
            # Equities: Sizing = target_risk / risk_distance
            shares = target_risk_dollars / risk_distance
            # Notional cap check
            max_shares = (equity * self.max_notional_pct) / entry_price
            final_shares = max(1.0, min(shares, max_shares))
            achieved_risk_pct = (final_shares * risk_distance) / equity
            return float(int(final_shares)), achieved_risk_pct

    def compute_entry_fill(self, instrument: Instrument, side: str, raw_price: float) -> Tuple[float, float]:
        """Compute entry price and entry slippage (Rule 2)."""
        if instrument.asset_type == "future":
            slip_amount = instrument.slippage_ticks * instrument.tick_size
        else:
            slip_amount = raw_price * (instrument.slippage_bps / 10000.0)

        slipped_price = raw_price + slip_amount if side == "long" else raw_price - slip_amount
        return slipped_price, slip_amount

    def compute_exit_fill(
        self,
        instrument: Instrument,
        side: str,
        raw_price: float,
        exit_reason: str,
    ) -> Tuple[float, float]:
        """Rule 4: Target exits are resting limit orders (NO slippage). Stops and time exits slip."""
        if exit_reason == "target":
            # Resting limit order: fills at limit price with 0 slippage
            return raw_price, 0.0

        # Stops, time exits, market close slip
        if instrument.asset_type == "future":
            slip_amount = instrument.slippage_ticks * instrument.tick_size
        else:
            slip_amount = raw_price * (instrument.slippage_bps / 10000.0)

        slipped_price = raw_price - slip_amount if side == "long" else raw_price + slip_amount
        return slipped_price, slip_amount

    def compute_fees(
        self,
        instrument: Instrument,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> Tuple[float, float]:
        """Rule 2: SEC Section 31 and FINRA TAF on equity sales, commissions on futures."""
        reg_fees = 0.0
        comm_fees = 0.0

        if instrument.asset_type == "future":
            # Futures commission per contract round-trip
            comm_fees = instrument.commission_per_contract * quantity * 2.0
        else:
            # Equity: zero commission, but regulatory fees apply on the SELL side
            # If long: sale occurs at exit
            # If short: sale occurs at entry
            sale_price = exit_price if side == "long" else entry_price
            sale_value = sale_price * quantity
            sec_fee = sale_value * instrument.sec_fee_rate
            finra_taf = min(instrument.finra_taf_cap, quantity * instrument.finra_taf_per_share)
            reg_fees = sec_fee + finra_taf

        return reg_fees, comm_fees

    def run_strategy(
        self,
        df_bars: pd.DataFrame,
        symbol: str,
        candidate_signals: List[Dict[str, Any]],
        arm_name: str = "rules",
    ) -> List[TradeRecord]:
        """Simulate trade execution using fast NumPy arrays (Rule 11).

        Args:
            df_bars: DataFrame of 5m bars with columns ['open', 'high', 'low', 'close']
            symbol: Ticker symbol
            candidate_signals: List of candidate dicts with:
                - 'entry_idx': bar index where signal confirmed
                - 'side': 'long' or 'short'
                - 'stop_price': stop level
                - 'target_price': target level
                - 'approved': bool from decider
        """
        instrument = self.get_instrument(symbol)
        
        # Rule 11: Extract numpy arrays for the fast loop
        n_bars = len(df_bars)
        opens = df_bars["open"].values
        highs = df_bars["high"].values
        lows = df_bars["low"].values
        closes = df_bars["close"].values
        timestamps = df_bars.index

        strategy_trades = []
        trade_id = len(self.trades) + 1

        for cand in candidate_signals:
            if not cand.get("approved", True):
                continue

            entry_idx = cand["entry_idx"]
            # Rule 1: Signal confirmed at entry_idx bar close.
            # Entry fills at entry_idx close at the earliest.
            side = cand["side"]
            raw_entry = closes[entry_idx]
            stop_price = cand["stop_price"]
            target_price = cand["target_price"]
            max_bars = cand.get("max_bars", 78)  # End of session

            slipped_entry, entry_slip_unit = self.compute_entry_fill(instrument, side, raw_entry)
            qty, achieved_risk = self.calculate_sizing(instrument, raw_entry, stop_price, self.capital)
            if qty <= 0:
                continue

            self.achieved_risks.append(achieved_risk)

            # Rule 1: Stops and targets are checked from NEXT bar onward (entry_idx + 1)
            exit_idx = None
            exit_reason = "time_exit"
            exit_price_raw = None
            was_ambiguous = False

            curr_idx = entry_idx + 1
            while curr_idx < n_bars and (curr_idx - entry_idx) <= max_bars:
                bar_h = highs[curr_idx]
                bar_l = lows[curr_idx]
                bar_c = closes[curr_idx]

                if side == "long":
                    hit_stop = bar_l <= stop_price
                    hit_target = bar_h >= target_price

                    if hit_stop and hit_target:
                        # Rule 5: Ambiguous bar -> resolve pessimistically as stop-first
                        was_ambiguous = True
                        self.ambiguous_bars_count += 1
                        exit_reason = "stop"
                        exit_price_raw = stop_price
                        exit_idx = curr_idx
                        break
                    elif hit_stop:
                        exit_reason = "stop"
                        exit_price_raw = stop_price
                        exit_idx = curr_idx
                        break
                    elif hit_target:
                        exit_reason = "target"
                        exit_price_raw = target_price
                        exit_idx = curr_idx
                        break

                else:  # short
                    hit_stop = bar_h >= stop_price
                    hit_target = bar_l <= target_price

                    if hit_stop and hit_target:
                        was_ambiguous = True
                        self.ambiguous_bars_count += 1
                        exit_reason = "stop"
                        exit_price_raw = stop_price
                        exit_idx = curr_idx
                        break
                    elif hit_stop:
                        exit_reason = "stop"
                        exit_price_raw = stop_price
                        exit_idx = curr_idx
                        break
                    elif hit_target:
                        exit_reason = "target"
                        exit_price_raw = target_price
                        exit_idx = curr_idx
                        break

                curr_idx += 1

            # Time exit / end of session fallback
            if exit_idx is None:
                exit_idx = min(n_bars - 1, entry_idx + max_bars)
                exit_reason = "time_exit"
                exit_price_raw = closes[exit_idx]

            slipped_exit, exit_slip_unit = self.compute_exit_fill(instrument, side, exit_price_raw, exit_reason)

            # Rule 3: Compute P&L before costs from unslipped prices
            mult = instrument.multiplier
            if side == "long":
                pnl_pre_cost = (exit_price_raw - raw_entry) * qty * mult
                pnl_net_raw = (slipped_exit - slipped_entry) * qty * mult
            else:
                pnl_pre_cost = (raw_entry - exit_price_raw) * qty * mult
                pnl_net_raw = (slipped_entry - slipped_exit) * qty * mult

            # Costs
            slippage_cost = abs(pnl_pre_cost - pnl_net_raw)
            reg_fees, comm_fees = self.compute_fees(instrument, side, slipped_entry, slipped_exit, qty)
            pnl_net = pnl_pre_cost - slippage_cost - reg_fees - comm_fees

            # Risk multiple (R)
            risk_dollars = abs(raw_entry - stop_price) * qty * mult
            r_mult = pnl_net / risk_dollars if risk_dollars > 0 else 0.0

            # Update capital
            self.capital += pnl_net

            record = TradeRecord(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                entry_time=timestamps[entry_idx],
                exit_time=timestamps[exit_idx],
                entry_price_raw=raw_entry,
                entry_price_slipped=slipped_entry,
                exit_price_raw=exit_price_raw,
                exit_price_slipped=slipped_exit,
                quantity=qty,
                stop_price=stop_price,
                target_price=target_price,
                exit_reason=exit_reason,
                pnl_pre_cost=pnl_pre_cost,
                slippage_cost=slippage_cost,
                regulatory_fees=reg_fees,
                commission_fees=comm_fees,
                pnl_net=pnl_net,
                r_multiple=r_mult,
                was_ambiguous_bar=was_ambiguous,
                holding_bars=exit_idx - entry_idx,
                arm=arm_name,
            )

            strategy_trades.append(record)
            self.trades.append(record)
            trade_id += 1

        return strategy_trades
