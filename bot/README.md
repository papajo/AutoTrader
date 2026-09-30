# 🤖 AutoTrader Bot: The Six AI Trading Agents

Nine modular components implementing Prompts 0 through 8 from `Build all six AI trading agents from scratch.md`.
Two of the six strategies make money, one is borderline, three are dead, and the dead ones are the most educational.

---

## 📋 The Nine Components

| # | Component | Focus / Strategy | Verdict / Result |
|---|-----------|------------------|------------------|
| **0** | **Foundation** (`bot/core/`) | Shared data, contracts, decision engine, execution, metrics | Required First (20 Non-Negotiable Rules) |
| **1** | **ORB + Jev** (`bot/strategies/orb/`) | Opening range breakout (15m range, 5m execution, 8 stocks) | **YES** (+0.110R, Sharpe 1.07) |
| **2** | **Insider Filings** (`bot/strategies/insider/`) | SEC Form 3/4/5 open-market officer purchases (K=10 book, 5d hold) | **YES** (+63% CAGR, alpha t=+2.54) |
| **3** | **Earnings Drift** (`bot/strategies/earnings_drift/`) | Post-earnings announcement drift on 40 mega-caps, hedged vs SPY | **YES** (Sharpe 3.10, -3.7% Max DD) |
| **4** | **Overnight Futures** (`bot/strategies/overnight_futures/`) | Liquidity sweeps on MES, MNQ, M2K, MYM with causal confirmation | **MAYBE** (Great on 2yr, flat on 16yr CME) |
| **5** | **News Scalp** (`bot/strategies/news_scalp/`) | 1st 5m bar earnings scalp; tape vs headline rank calibration | **NO** (Tape volume ranks better than text) |
| **6** | **Lunar & Gann** (`bot/strategies/lunar_gann/`) | Astronomical ephemeris tested against 30 shifted placebos | **NO** (Post-publication decay, luck) |
| **7** | **Validation Pass** (`bot/validation/`) | Rigorous significance, 95% CIs, power calculations, mechanical audit | The one that matters |
| **8** | **Offline Reports** (`bot/reports/`) | Self-contained HTML reports with pure inline SVG visualizations | Reports in `reports/out/` |

---

## 🛡️ The 20 Non-Negotiable Backtesting Rules

Every module in `bot/` strictly adheres to the 20 rules:
1. **No same-bar lookahead**: Signals at bar close fill at close; stops checked from NEXT bar onward.
2. **Realistic friction**: Slippage in bps/ticks + SEC Section 31 fee + FINRA TAF on equity sales.
3. **P&L reporting**: Separate pre-cost and net P&L without double counting slippage.
4. **Resting limit orders**: Profit target exits do NOT slip; stops and time exits slip as market orders.
5. **Ambiguous bars**: Bars touching both stop and target resolved pessimistically as stop-first.
6. **Risk-based sizing**: Comparable R units across all trades with achieved risk % reporting.
7. **Futures margin sizing**: Sized against margin (not notional), handling < 1 contract.
8. **No missing values as 0.0**: Drop candidate and warm-up history.
9. **Higher-timeframe shift**: Slow series shifted forward one of its own bars before reindexing.
10. **Futures session hours**: 18:00 to 17:00 ET with 6-hour clock shift.
11. **NumPy loops**: Fast NumPy arrays in the per-bar loop (no slow `DataFrame.loc`).
12. **Model response caching**: SHA-256 hash caching, full decision stream logged to JSONL.
13. **Network retries**: Retries with backoff on `OSError` and `HTTPException`.
14. **Three arms**: Rules (all), Gated (filters), Model (Jev).
15. **Threshold on probabilities**: Threshold on `probabilities[chosen_action]`, NOT raw confidence.
16. **Significance & CIs**: t-stats, 95% confidence intervals, power calculations, out-of-sample splits.
17. **Full-range ranking**: Measure ranking power across approved AND rejected trades.
18. **Never tune on buckets**: Promising buckets treated as hypotheses.
19. **Placebo scans**: Calendar anomalies tested against shifted-calendar placebos and holdouts.
20. **Benchmark selection as result**: Russell 2000 for small-caps, S&P 500 for mega-caps.

---

## 🚀 Running Strategies, Validation & Reports

### 1. Run Strategy 1 (ORB + Jev)
```bash
python3 -c "
from bot.strategies.orb import ORBStrategy
orb = ORBStrategy()
res = orb.run_all_three_arms('SPY')
print('Rules Avg R:', res['rules']['metrics']['avg_r'])
print('Gated Avg R:', res['gated']['metrics']['avg_r'])
print('Jev Avg R  :', res['jev']['metrics']['avg_r'])
"
```

### 2. Run Prompt 7 Statistical Validation Pass
```bash
python3 -m bot.validation.run_validation
```

### 3. Generate Offline SVG Reports
```bash
python3 -m bot.reports.build
```
Open `reports/out/index.html` in any browser to inspect the visual dashboards offline.

---

## 🧪 Running the Unit Tests

```bash
python3 -m pytest bot/tests/ -v
```
