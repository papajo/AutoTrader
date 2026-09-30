# Build all six AI trading agents from scratch

Nine copy-paste prompts. Paste each into a fresh Claude Code session and it builds, backtests and honestly grades one trading strategy. Two of the six make money, one is borderline, three are dead, and the dead ones are the most useful.

Everything here comes from actually building it. The prompts carry the twenty-odd rules and fourteen bugs that came out of that, because a fresh Claude will write most of those bugs unless it is told not to, and every one of them makes results look better than they are.

---

## What you need

| thing | where | cost |
| ----- | ----- | ----- |
| Claude Code | claude.com/claude-code | subscription |
| Jev API key | console.typesafe.ai/keys | \$0.042 per million input tokens, output free |
| Alpaca paper keys | app.alpaca.markets | free |
| Python 3.9+ | pip install pandas numpy alpaca-py scipy yfinance | free |
| SEC data | data.sec.gov, no key | free |

Total AI spend for all six agents, end to end: about 40 cents. Roughly 5,000 Jev decisions at 280 ms each. The expensive part is your time, not the models.

Optional, only for agent 2: a futures data source. QuantConnect's free tier gives CME history back to 2010 and is the reason agent 2 got caught.

---

## The nine prompts

| \# | prompt | what it builds | result |
| ----- | ----- | ----- | ----- |
| 0 | Foundation | shared data, decision and execution engine | required first |
| 1 | Opening range breakout \+ Jev | 8 stocks, intraday | profitable |
| 2 | Insider filings | whole market, 5-day holds | profitable |
| 3 | Earnings drift | 40 mega caps, 10-day hedged | profitable |
| 4 | Overnight futures | ES, NQ, RTY, YM | two good years, sixteen flat |
| 5 | News scalp | earnings gaps, first minutes | no edge |
| 6 | Lunar and Gann | SPY, QQQ daily | luck |
| 7 | Validation pass | run against any agent above | the one that matters |
| 8 | Reports | self-contained HTML per agent | for publishing |

Run 0 first. After that, any of 1 to 6 in any order. Run 7 against each one before believing anything. Do not skip 7\.

---

## The rules every prompt inherits

Paste this block at the top of any prompt if you are building something not covered here. These are not style preferences. Each one is a bug that produced a wrong answer during the original build.

BACKTESTING RULES, NON-NEGOTIABLE

1\.  No same-bar lookahead. A signal from the bar closing at 09:45 fills at 09:45's  
    close at the earliest, and stops are checked from the NEXT bar onward.  
2\.  Model friction per side: slippage in basis points or ticks, plus the SEC  
    Section 31 fee and FINRA TAF on equity sales. Alpaca commission is genuinely  
    zero, which is why everything else gets forgotten.  
3\.  Report P\&L before costs SEPARATELY from net. Compute pre-cost P\&L from  
    unslipped prices. Do not subtract slippage from a figure that already contains  
    slipped fills; that double counts.  
4\.  Target exits are resting limit orders and do NOT slip. Only stops and time  
    exits become market orders. Slipping every exit overstates friction on roughly  
    half the trades of a target-based strategy.  
5\.  Count ambiguous bars: when one bar's range covers both stop and target, nobody  
    knows which came first without tick data. Resolve pessimistically as stop-first  
    and report the count. A large count means the result is noise.  
6\.  Risk-based sizing, so R is comparable across trades. Report the achieved  
    average risk as a percentage of equity: if a notional cap binds it will  
    silently shrink your real risk and understate returns.  
7\.  For futures, size against MARGIN not notional, and handle the case where the  
    risk budget buys less than one contract. Silently dropping those trades biases  
    the sample toward narrow-range sessions.  
8\.  Never render a missing indicator value as 0.0 into text a model will read.  
    "price is \+0.00 ATR from the 200 EMA" when the EMA does not exist yet is a  
    fabricated fact. Drop the candidate instead, and fetch warm-up history.  
9\.  Higher-timeframe values must be shifted forward one of their own bars before  
    reindexing onto a faster series. A 15-minute bar stamped 09:30 is only complete  
    at 09:45.  
10\. Futures sessions run 18:00 to 17:00 ET. Grouping by calendar midnight splits  
    every session and corrupts the prior-session range.  
11\. Use numpy arrays in the per-bar loop, not DataFrame.loc. A .loc lookup per  
    symbol per bar costs about 50 microseconds: invisible once, fatal across a sweep.  
12\. Cache every model response keyed by a hash of the exact request, and log the  
    full decision stream including rejections. A black box has no business in a  
    backtest you cannot reproduce, and you need the rejections for rule 17\.  
13\. Retry network calls on OSError and http.client.HTTPException, not just  
    URLError. A long sequential run will meet dropped keep-alives, and a  
    RemoteDisconnected that escapes your handler kills the whole run mid-flight.  
14\. Three arms on every strategy: rules (take everything), gated (hand-written  
    filters) and the model. The gated arm is the control. Any filter that removes  
    trades moves the win rate, so "the AI improved it" is unfalsifiable without it.  
15\. Threshold on probabilities\[chosen\_action\]. Do NOT use the model's confidence  
    field as a quality signal: it measures how concentrated the distribution is and  
    it tested significant in the WRONG direction.  
16\. Always split train and test by time, report t-statistics and confidence  
    intervals, and run a power calculation. If a confidence interval contains zero,  
    say so in the same sentence as the headline number.  
17\. Measure a score's ranking power across its FULL range, including candidates it  
    rejected. Measuring only among approved trades is restriction of range and it  
    turned a real, significant relationship into an apparently absent one.  
18\. Never tune on buckets. Some hold a dozen trades. Anything promising is a  
    hypothesis for a period you have not looked at.  
19\. For any calendar or seasonal strategy, test against shifted-calendar placebos  
    AND on symbols held back from development. Both are cheap and both kill things.  
20\. Benchmark choice is a result. Small-cap strategies measured against the S\&P  
    look negative in a mega-cap decade; use the Russell. State which you used.

Two facts about the platform that save an afternoon: Alpaca cannot trade futures, and yfinance CME futures data is flagged 10 minutes delayed (exchangeDataDelayedBy), which is accurate enough for backtests and useless for live triggers.

---

## Prompt 0: the foundation

Build a shared backtesting foundation in Python 3.9 that several trading strategies will plug into. Structure it so the strategy, the decision layer and the execution engine know nothing about each other.

Credentials from a gitignored .env: ALPACA\_PAPER\_KEY, ALPACA\_PAPER\_SECRET, TYPESAFE\_API\_KEY. Write a .env.example with empty values.

core/data.py: Alpaca historical bars via StockHistoricalDataClient, SIP feed, cached to pickle per symbol and date range. Convert to America/New\_York and filter to the regular session. Verify you get 78 bars per day at 5-minute resolution; more means pre-market bars with garbage spreads are in your sample.

core/features.py: ATR, EMA, session VWAP, resampling, and a higher-timeframe alignment helper that shifts the slow series forward one of its own bars before reindexing. Trailing windows only, everywhere.

core/contracts.py: the strategy-to-decider contract. A Snapshot carries the symbol, timestamp, price, the action the strategy proposes, a dict of numeric features, and a list of plain-English context lines. Features are what hand-written gates read; context lines are what the model reads. Both built from the same row so neither layer gets an information advantage. Do NOT name this file types.py: it shadows the standard library and the import error is baffling.

core/decision.py: three implementations behind one interface. RuleDecider takes every candidate. GateDecider takes a list of veto functions. JevDecider calls POST https://api.typesafe.ai/v1/systemone with {"model": "jev-latest", "state": "\<text\>", "questions": {...}} and reads {"answers": {id: {"choice", "confidence", "probabilities"}}, "usage"}. Question types are choice (with a criteria map), score (with a criteria list) and noul. Call it over stdlib urllib, not the official typesafe-sdk, which needs Python 3.10+ while pandas and alpaca-py here are on 3.9. Cache every response keyed by a SHA of the exact request. Log every decision, including refusals, to JSONL. Support concurrent prefetch on a thread pool: the rate limit is 1,200 requests a minute, so about five workers sits just under it. Retry with backoff, catching OSError and http.client.HTTPException.

core/engine.py: a portfolio executor iterating one merged, time-ordered event stream across symbols. Implement rules 1 to 11 from the block above. Include an Instrument abstraction so the same engine costs equities in basis points with regulatory fees, and futures in ticks with a contract multiplier, per-contract commission and margin-based sizing. Ship MES, MNQ, M2K, MYM and ES presets.

core/metrics.py: trades, win rate, target hit rate, sum of R, average R, expectancy, profit factor, total return, CAGR, max drawdown from a daily equity curve, Sharpe, Sortino, average hold, and the cost stack as pre-cost P\&L, slippage, fees, net. Report sum of R prominently: it is independent of position sizing.

Smoke test the data layer and print the bars-per-day check.  
---

## Prompt 1: opening range breakout, filtered by Jev

This is the one where the AI layer earns its keep. Keep the arc: the naked strategy barely pays, the standard advice makes it worse, the model fixes it.

Using the foundation, build an opening range breakout on US stocks and run it through all three decision arms.

Strategy. The opening range is the high and low of the first 15 minutes after 09:30 ET; make it a parameter but default to 15, not 5\. Execute on 5-minute bars. Skip the day unless the range is between 0.5 and 2.0 ATR, measured on bars of the opening-range size over 14 sessions. Derive that ATR period from session length rather than copying a constant from a tutorial: a US equity session has 26 fifteen-minute bars, so 14 days is 364, not the 1344 you will see written for 24-hour instruments.

Confirmation: the PREVIOUS bar closed inside the range AND this bar closed outside it, strictly. Checking only the breakout bar's open misses days that gap straight through. A close exactly ON the level does not count as through it. Entry at the confirming bar's close, stop at the opposite edge of the opening range, target at stop distance times 2\. No entries after 11:45, one attempt per symbol per day, flat before the close.

Context for the decision layers. Opening range size in ATR, how far past the edge the close sits, alignment with the 50 and 200 EMA on the opening-range timeframe, distance to each EMA in ATR, breakout bar volume against the 20-day average for that same time of day (not a flat session average, because 09:30 volume is nothing like 14:00 volume), candle body and wick percentages, how many times the edge was tested first, the overnight gap, distance to yesterday's high and low, whether the opening range sits inside yesterday's range, and the distance to the next round number in the trade's direction. Apply rule 8: drop any candidate whose context is not yet warm, and fetch 45 extra calendar days.

Arms. Rules takes every breakout. Gated implements the advice every trading channel gives: skip counter-trend breakouts, weak-bodied candles, breakouts that already ran, and over-tested edges. Jev gets one choice question (enter long, enter short, wait) plus two recorded-but-never-acted-on questions: a score for how likely this is a fakeout, and a noul for whether the higher timeframe supports the direction. Threshold at 0.30, not 0.55. Never let the model flip the side the strategy proposed; that is a different strategy.

Run on SPY QQQ IWM AAPL MSFT NVDA TSLA AMD from 2023-01-01 to now, all three arms, then show me the comparison and the cost waterfall per arm.  
Expected results. About 3,110 candidates. If yours differ by more than about 10% something upstream is different, which is fine, but the shape should match:

arm            trades   win rate   avg R    return   max DD   Sharpe   net  
rules           2,370     43.9%   \+0.014    \+7.3%   \-18.6%    0.20    \+$728gated1,41644.6%+0.013+2.9%-15.3%0.13+$292  
jev @ 0.30        696     49.3%   \+0.110   \+37.8%    \-7.0%    1.07   \+\$3,782

The gated arm being WORSE than taking everything is the point, not an error: three of its five filters veto groups that were actually profitable. The Jev arm's per-trade edge is \+0.110R at t=+2.52 and holds across a train/test split (+0.108 then \+0.115). Jev is still not provably better than the gates at t=+1.82.

The trap. Measure Jev's calibration on all 2,370 candidates, not just the 696 it approved. Full range gives Spearman \+0.066 at p=0.0013; among approved trades only it gives p=0.48 and looks like nothing. That is rule 17 and it nearly caused the whole result to be dismissed.

---

## Prompt 2: corporate insider filings

The strongest statistical result of the six, and the simplest rule.

Build a strategy on corporate insider purchases using the SEC's bulk Form 3/4/5 datasets.

Data. Download the quarterly zips from https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{YYYY}q{Q}\_form345.zip for 2019Q1 onward. Each contains NONDERIV\_TRANS.tsv, SUBMISSION.tsv and REPORTINGOWNER.tsv. Keep only open-market purchases: TRANS\_CODE 'P', TRANS\_ACQUIRED\_DISP\_CD 'A', and a security title matching common or ordinary stock. Bound the values to plausible trades (price between \$0.50 and \$10,000, total value under \$500M): fat-finger filings with prices of 100000 or share counts in the billions are common and will dominate any sum. Join owner relationship and title to flag officer, director, ten percent owner, and CEO/CFO/President.

Prices. Alpaca daily bars with adjustment="all", in 200-symbol batches. Expect roughly 5,900 tickers and prices for about 5,600 of them.

Event. One row per ticker and filing date. Entry at the OPEN of the session after the filing date. Filings accepted after 17:30 ET carry the next business day as their filing date, so next-open is the conservative choice that cannot leak.

Study first, trade second. Excess return over the benchmark at 5, 20, 60 and 120 sessions, sliced by role, dollar value, cluster size and liquidity tercile. Benchmark against IWM, and also run it against SPY so you can see rule 20 in action: measured against the S\&P every small-cap slice looks negative in this period, purely because large caps beat small caps.

Then a book. Each session, free slots equals K minus open positions; take up to that many new qualifying filings, largest first, at the next open, equal weight 1/K of equity, hold exactly H sessions, pay a round-trip cost. Mark the book to market daily using each position's close: a realized-only curve understates both beta and drawdown. Regress the daily book return on the benchmark and report beta, alpha and t(alpha). Split train and test by time. Sweep the cost from 10 to 80 basis points.

Run it with officer purchases of at least \$10,000, K=10, hold 5\.  
Expected results. About 106,700 purchases, 55,500 ticker-day events, 51,600 with forward data.

five-session excess over IWM       n         mean      t  
officer (any)                   18,691     \+0.72%    \+8.1  
CEO / CFO / President            9,545     \+0.66%    \+4.8  
director only                                \+0.5%     \~  
ten percent owner               15,562     \+0.66%    \+7.0  then NEGATIVE at 60d

marked-to-market book, officer \>= \$10k, K=10, hold 5, 30 bps  
                     CAGR    max DD   Sharpe   beta   alpha/yr   t(alpha)  
train 2019-23H1      \+73%      \-41%    1.57    0.97     \+67%      \+3.60  
test  2023H2-26      \+63%      \-24%    1.65    0.81     \+53%      \+2.54  
at 60 bps, test      \+41%      \-26%    1.20    0.81     \+32%      \+1.66  
Russell 2000, test   \+12%      \-28%

Three things to verify rather than assume. Survivorship: only about 4.6% of events should lack prices, and roughly a third of tickers should have histories that END before the present, which confirms delisted names are included. Per-year: average net per trade should be positive in every year including 2022\. And the "smarter" subsets, CEO-only and over \$100,000, should do WORSE out of sample than taking every officer. If they look better in yours, you are probably fitting.

What this is not. Every 60 and 120 session slice flips sign between halves and their medians are negative. There is no multi-month "insiders know the future" drift in this data. It is a one-week reaction to the filing becoming public.

---

## Prompt 3: post-earnings drift

The oldest anomaly in the book, and the only one here where costs do not matter.

Build a post-earnings-announcement drift strategy on mega caps.

Events. SEC EDGAR submissions API, https://data.sec.gov/submissions/CIK{cik}.json with a descriptive User-Agent. Take 8-K filings whose items contain 2.02, which is the earnings release. acceptanceDateTime gives the second it became public, so classify each release as premarket, intraday or after-hours and compute the first tradable session from that.

Trade. At the open of that first tradable session, take the direction of the gap from the prior close. No profit target. Exit at the open 10 sessions later. Disaster stop only, three gap-widths away. Short an equal notional of SPY against each position so the market is hedged out and what is left is the drift. Size by NOTIONAL, about 5% of equity per event: risk-based sizing inverts this edge, because it puts the most money into the smallest gaps.

Run the event study first, unhedged and hedged, at 1, 5, 10, 20 and 40 sessions, sign-adjusted for the gap direction, sliced by gap size. Then build the engine version and check the two agree.

Universe: the 40 largest and most-covered US names. Also run a 150-name universe so you can see the boundary. Period 2019 onward, split by time.  
Expected results.

event study, excess over SPY, sign-adjusted    n      5d      10d     20d  
all gaps \>= 0.5%                              563   \+0.55%  \+0.64%  \+0.82%  
                                                     t=2.75  t=2.48  t=2.15  
gaps \>= 5%                                    219   \+1.03%  \+1.37%  \+1.84%  
                                                     t=3.06  t=2.95  t=2.54

traded, 40 names, gap \>= 5%, hold 10, hedged  
370 events, \+1.27% per event, profit factor 1.58, Sharpe 3.1, max DD \-3.7%  
positive in EVERY year including 2025 and 2026; test half stronger than train  
150-name universe at the same gap threshold: NEGATIVE

Day one is a coin flip. The drift starts on day two, is finished by session 10 to 20, and is noise past 40\. Gap size is the only narrowing that survives: ticker leaderboards, repeat offenders, gap direction, release timing and day-one confirmation are all noise. Friction is about \$0.45 per event on a ten-day hold, so this is the one strategy where fills are not the deciding factor.

---

## Prompt 4: the overnight futures reversal

Build this one to learn what a convincing result that is still wrong looks like.

Build a liquidity-sweep reversal on index futures, traded around the clock.

Data. Continuous front-month 5-minute bars for ES, NQ, RTY and YM. Stitch quarterly contracts across their active windows. Sessions run 18:00 to 17:00 ET: shift the clock forward six hours so 18:00 becomes the start of the session day, or every prior-session range will be wrong.

Setup. Price sweeps one side of the prior session's range, then CLOSES back inside it, then closes across the 25% retracement, which is the entry. Stop at the 12.5% level, first target at the 50% retracement, so risk is 12.5% of the range and the first target is 2R. Skip sessions whose prior range is implausibly small or large. One attempt per side per session. Flat before the session ends.

Size as micros (MES, MNQ, M2K, MYM). Full-size contracts risk about 4.5% of a \$10,000 account per trade, which is unusable; micros land near 0.5%. Handle the case where the risk budget buys less than one contract.

Then the two filters that matter. First, record which session block each trigger falls in: Asia 18:00 to 03:00, Europe 03:00 to 09:30, US 09:30 to 16:00. Second, for each trigger, count how many of the OTHER indices had already swept AND closed back inside their own prior range, read as of that bar and not later in the session. That second one is the difference between a market-wide liquidity grab and one contract's idiosyncratic flow, and getting it causal rather than hindsight is the whole trick.

Report all sessions against Asia-only, and by how many other indices confirmed.  
Expected results on about two years of data.

all sessions, every trade      1,147 trades   \+0.009R    max DD \-14%  
Asia session only                174 trades   \+0.219R    max DD  \-5%  
Asia \+ at least one confirming   135 trades   \+0.262R  t=+2.44   \+26.2%, DD \-6.0%  
by confirming indices:  1 of 3 \+0.114R   2 of 3 \+0.105R   3 of 3 \+0.447R (t=+2.75)

That looks excellent. It replicates on all four instruments independently, both halves of the window are positive, and it survives five times the assumed slippage. Now extend the history. Port the identical rules to QuantConnect, whose free tier has CME data back to 2010, verify the port reproduces your engine trade-for-trade on the overlapping window, and run it from 2010\.

2019-05 to 2026-06, micros          433 trades   \-0.007R  
2019 to 2024 only                   334 trades   \-0.061R  
2010 to 2026, full-size             806 trades   \-0.041R   t=-0.91  
2010 to 2026, all 3 confirmed       196 trades   \+0.159R   t=+1.70

Negative in eight of the nine years before 2019\. The two good years sit inside one of only two periods in sixteen where this worked, both unusually volatile overnight. Every check available inside the two-year window passes, and only more data catches it. That is the lesson, and no amount of cleverness substitutes for it.

Improvements that were tested and refuted, so you do not spend a day on them: a resting order at the level instead of waiting for a close (16 times worse, because the close confirmation is doing real work), waiting for a retrace, re-entry after a stop, five-timeframe continuity, Strat bar combinations, broadening formations, stop widths from 12.5% to 37.5%, and the model as a selector in three prompt designs. Requiring the full confluence checklist at once produces exactly zero trades, because each condition is individually rare.

---

## Prompt 5:

##  the news scalp (DOESNT WORK. Can Still work off of)

The premise of every AI trading video. Build it so you can say what it is worth.

Build an earnings-gap scalp and test whether reading the headlines beats reading the tape.

Events from EDGAR 8-K item 2.02 as in prompt 3\. Headlines from Alpaca's news API, https://data.alpaca.markets/v1beta1/news, which has second-resolution timestamps back to at least 2016\. Call the REST endpoint directly: the Python SDK hides the paging token and will silently truncate a busy symbol's month at the first page or two. Pace to about three requests a second and back off on 429\.

Trade: at the close of the first 5-minute bar of the first tradable session, take the gap's direction. Stop beyond the opening drive's extreme, not a multiple of the prior session's ATR: on earnings days an ATR stop is several times too small and gets resolved by noise on the second bar. Target at 1.5R, flat by the close.

Three arms. Rules takes every gap. Gated requires regex keyword sentiment (beats, misses, raises, cuts) to agree with the gap direction. Jev gets the actual headlines published between the filing and the entry bar, plus the tape context, and one choice question with two recorded score questions for how the results read and whether the gap already priced the news.

Then shadow-calibrate: join every Jev decision to the unfiltered arm's outcome and rank-correlate its probability, its confidence, each score, the keyword score, the gap size and the first-bar volume against realised R.  
Expected results. 557 tradeable gaps out of about 630 releases.

arm                              trades   avg R    net  
rules, every gap                    550   \-0.078   \-$1,661gated,keywordsagree225-0.045-$371  
jev, reads the headlines             17   \+0.076      \+$54tapeonly,gap>=2%andvol>=3x322-0.004-$84   (fails out of sample)

ranking power against realised R (Spearman, all 557 candidates)  
first-bar volume   \+0.200  p\<0.0001  
gap size           \+0.165  p=0.0001  
Jev's probability  \+0.088  p=0.04, non-monotonic  
keyword score      \+0.025  p=0.56

Jev refuses 97% of these, which in aggregate is correct because following gaps loses money. But two numbers off the price tape rank outcomes better than the model that read the sentences. The horizon was the mistake, not the idea: the same events held ten days and hedged are prompt 3, which works.

Optional extra in the same session: congressional disclosures from the house-stock-watcher dataset. Anchor to the DISCLOSURE date, never the transaction date, because members have up to 45 days to file. Expect \+0.40% over 20 sessions on about 1,330 buys over \$15,000, a little more for buys over \$100,000, and a per-member track record that does not predict the next trade at all and inverts out of sample.

---

## Prompt 6: lunar phase and Gann geometry (DOESNT WORK. Can Still work off of)

The most-requested idea in trading content, almost never tested honestly.

Build a lunar-phase strategy on daily bars and try to break it.

Compute new and full moon dates from an ephemeris, not a lookup table, and unit test them against a known source. Enter at the close of a new or full moon bar, direction from a lunar trend rule, stop and target in ATR, time exit after 10 bars. Optionally overlay Gann levels in eighths off confirmed pivots.

Then run every test that could kill it, in this order:

1. A PLACEBO arm: identical logic on calendars shifted by a fixed number of days. If it cannot beat its own placebo, the calendar is doing nothing.  
2. A shift scan: rank the true calendar against 30 shifted ones.  
3. Symbols held back from development. Pick them before you look.  
4. Index history back to 1950 from any free daily source.  
5. The same effect on nine world indexes, before and after the year the effect was published.

Expected results. On SPY and QQQ from 2016, about 156 trades, \+0.26R, profit factor 1.63, t=2.6, placebo flat, true calendar ranked 2nd of 30\. That looks real. Then: untouched symbols give profit factor 1.02 and rank 27th of 30\. The S\&P back to 1950 gives 1,089 pre-2016 events at profit factor 1.09, ranked 20th of 30\. The one genuine effect in the literature, slightly higher returns within a few days of a new moon, was positive on nine of nine world indexes before 2016 and INVERTED on nine of nine after. That is post-publication decay, and it is the cleanest example of it you will find.

Asked to judge these setups, Jev stands aside 86% of the time with zero calibration, correctly: the signal is about 5 basis points against 100 basis points of daily noise. There is nothing there to combine.

---

## Prompt 7: the validation pass 

Run this against every agent above. It is the prompt that separates a backtest from a screenshot, and it is the one most people skip.

The strategy runs. Now find out whether the result means anything. Do not tune anything to improve the numbers. Your job is to try to break it.

1. Scale the sample. More symbols, more years, until you have enough trades to say something. Report how many you have.  
2. Significance. Per-trade mean, standard deviation, standard error, t-statistic against zero, and a 95% confidence interval. Then the same for the DIFFERENCE between arms, using the standard error of the difference. If a confidence interval contains zero, say so in the same sentence as the headline. A Sharpe of 3 on 27 trades is noise wearing a suit.  
3. A proportion test on win rate between arms, because a win-rate difference can be significant when a per-trade difference is not.  
4. Power. Given the observed standard deviation, how many trades would you need to detect the observed effect at 80% power? If you have fewer, the honest answer is "not yet known", not a smaller claim.  
5. Out-of-sample split by time, roughly two thirds. Report every arm on both halves. Stability across halves is worth more than a high number overall.  
6. A parameter sweep with the split built in. Every configuration scored on BOTH halves. Add a column for profitable-after-costs in both periods, and expect it to be zero or close to it.  
7. Where it bleeds. Slice by every feature recorded. Then say out loud which of your hand-written filters are vetoing profitable groups. Treat every bucket as a hypothesis, not a setting.  
8. Friction. The cost stack per arm, then the result at 0, 0.5, 1, 2 and 5 times the assumed slippage. Verify this formula on your own data: friction in units of risk \= 2 x slippage\_bps x price / stop distance, and check its prediction that wider stops relative to price lose proportionally less.  
9. Shadow calibration. Join every model decision, including refusals, to the unfiltered arm's outcome and rank-correlate every answer it gave. State the expected direction of each BEFORE looking.  
10. A mechanical audit. Re-derive every level from raw bars and assert each trade satisfies each rule: preconditions in order, fill where it should be, stop and target at the exact levels, the exit bar actually reached the price, inside the trading window. Report N of N.  
11. Write it down. An ITERATIONS.md with the configuration, the results, what is established with its statistical test, what is NOT established and why, and every bug found. Commit and tag it.

Then tell me which claims I am allowed to make out loud and which I am not.  
---

## Prompt 8: the reports

Build a report generator that writes one self-contained HTML file per strategy into reports/out/, plus an overview index. No CDN, no server, opens offline, type large enough to read on video.

reports/viz\_core.py holds shared primitives as inline SVG: overlaid equity curves with optional log scale, horizontal and vertical bar panels, cost waterfalls, big-number scorecards, a left-to-right progression chain for before-and-after stories, sortable metric tables, and a verdict panel whose rows are marked yes, maybe or no. One accent colour per arm held across every chart; green means made money and red means lost money, never decoration.

reports/build.py reads each strategy's summary JSON, trade CSVs, equity curves and decision logs and assembles the pages. Every figure comes from a file on disk. Where a statistic was computed in a validation run rather than saved, cite where it came from in the text.

Every page ends with a "reading the fine print" panel listing what the numbers do and do not prove, including the things that are NOT established. Lead each page with the most interesting true thing, not the verdict.  
---

