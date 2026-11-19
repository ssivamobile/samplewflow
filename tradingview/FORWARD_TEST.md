# Forward test: KOF levels + Model 1 screener on six liquid US ETFs / stocks

Pre-registered 2026-11-19, before any trade was logged. Changing anything below after the first
logged trade starts a new test (re-freeze, new row set). Numbers marked *default* were chosen by
Claude on the user's instruction "use your defaults"; they are not from the article.

**Revision.** v1 (QQQ only, confluence tolerance 0.01%) was superseded the same day, before any trade, after a
20-session count showed it would fire about 0.1 times per symbol-session (see "Why v2"). The user chose to widen
both the tolerance and the universe. This file is v2; freeze #3 supersedes freezes #1 (MNQ) and #2 (QQQ v1).

## Decisions (Step 0)
| Item | Value | Source |
|---|---|---|
| Universe | SPY, QQQ, IWM, NVDA, TSLA, MSFT. No other symbols in this test. | user (option 4) |
| Chart | TradingView, 5-minute, ETH (extended hours) so overnight levels exist; 2-3 minute not validated | default |
| Session | RTH 09:30-16:00 ET | article |
| Opening range | 5 minutes (09:30-09:35) | user |
| Overnight levels | 16:00-09:29 ET (after-hours + pre-market) | default |
| Value area | 70%, two-row expansion from POC, volume from 1-minute bars | validated against TradingView SVP |
| Bin size | 4 ticks = 0.04 on every symbol | validated, see below |
| Confluence / touch tolerance | **0.05% of price** (about 0.33 on QQQ, 0.37 on SPY, 0.25 on NVDA) | user (widened from 0.01%) |
| Candidate window / warm-up / min R to TP2 / max per symbol per day | 09:30-12:30 / 30 min / 2.0 / 3 | script defaults |
| Stop / targets | beyond sweep extreme + 0.5 x 21-bar range; TP1 = (VAH+VAL)/2, TP2 = opposite edge; stop to breakeven after TP1 | article / script |
| Costs | 0.02 per share round trip (spread + commission + slippage) | default assumption |
| Simulator | TradingView Paper Trading (nothing live) | user |

## Why v2 (measured 2026-11-19, last 20 RTH sessions 2026-10-22..2026-11-18, TradingView data)
Funnel: raw poke-and-re-enter -> slot free -> two tools overlap -> opened (R to TP2 >= 2).

| Symbol | Tol 0.01% (v1) | Tol 0.05% (v2) |
|---|---|---|
| QQQ | 122 / 121 / 2 / **2** | 122 / 113 / 27 / **7** |
| SPY | 138 / 137 / 4 / **1** | 138 / 125 / 27 / **10** |
| IWM | 115 / 115 / 2 / **2** | 115 / 107 / 13 / **6** |
| NVDA | 120 / 117 / 2 / **2** | 120 / 114 / 13 / **4** |
| TSLA | 117 / 116 / 4 / **1** | 117 / 110 / 18 / **7** |
| MSFT | 116 / 113 / 5 / **4** | 116 / 108 / 13 / **6** |
| Total opened | 12 (0.1 per symbol-session) | **40 (about 2.0 per session across the six)** |

The two-tool overlap removes most candidates, and its tolerance is a placeholder the article does not specify.
At 0.05% the test is feasible: about 100 setups in 50 sessions (roughly 10 weeks), 50 closed trades in about 25.
Widening the tolerance changes what "two tools line up" means; a result from v2 does not transfer to a tighter definition.

## Validation behind the profile (Pine minus TradingView SVP, price units, Nov 18 unless stated)
| Symbol | VAH | VAL | POC |
|---|---|---|---|
| QQQ (Nov 13 / 16 / 17 / 18) | -0.02 / 0.00 / +0.05 / -0.01 | -0.10 / -0.04 / -0.03 / -0.05 | -0.06 / +0.04 / +0.37 / -0.05 |
| SPY | +0.01 | -0.03 | +0.17 |
| IWM | -0.13 | -0.13 | -0.01 |
| NVDA | +0.08 | +0.04 | 0.00 |
| TSLA | -0.04 | -0.08 | 0.00 |
| MSFT | 0.00 | -0.04 | -0.04 |

POC is the least stable level. One session per symbol except QQQ. A low-priced stock (SOFI, 14.11) failed this
check (VAH off by 0.11, about 27% of the day's range), which is why the universe is limited to the six above.
MNQ scattered 0-3 points against SVP, which is one reason the futures setup was dropped.

## What counts as a setup
Every Model 1 candidate the screener raises on one of the six symbols, and every setup the trader notices by eye.
Log it the moment it appears, **taken or skipped**, with `journal.py add` (`--symbol` is required). A skipped
setup needs a reason. Day type is judged live, before the outcome. Absorption, big trade and delta are confirmed by
eye (the script does not detect them).

## Execution rules (user instruction 2026-11-19, before any trade)
- **Paper only.** Orders go through TradingView **Paper Trading** and nowhere else. Before each order the
  Trade panel must read "Paper Trading". No real broker, no other account, ever. If the panel shows anything
  else, no order is placed.
- **Take every mechanical candidate** from a Model 1 alert of the frozen script on one of the six symbols,
  inside the 09:30-12:30 window, subject to the **daily cap below**. The only reasons to skip are mechanical
  (outside window, daily cap, paper account unavailable, data delayed or stale). Skips are logged with a reason.
- **Daily cap: at most 3 taken trades per day across all six symbols** (the article's 2-3 a day), first come
  first served. Further candidates that day are logged as skipped with reason "daily cap". `journal.py add`
  enforces this using the New York date.
- **Confirmations are recorded, not used as a filter.** Absorption / big trade / delta are judged by eye from the
  footprint and logged (`yes` / `no` / `unknown`). `journal.py stats` then compares confirmed vs not confirmed.
- **Entry / size.** Market order at the open of the bar after the alert, in the direction of the candidate.
  Risk per trade is a fixed $100 on the paper account: shares = floor(100 / risk per share), where risk per share =
  |entry - stop|. Split into two halves.
- **Exits.** Stop at the script's stop for both halves. Half exits at TP1 = (VAH+VAL)/2, half at TP2 = opposite
  value-area edge. When TP1 fills, the remaining half's stop moves to entry (breakeven). If the stop and a target
  are touched in the same bar, count the stop first (as the script does).
- **Journal R** is the blended R of the two halves: (R_half1 + R_half2) / 2, entered with `--r`; `--tp1-hit` and
  `--tp2-hit` record which targets filled; the 0.02 per share cost is subtracted by `journal.py`.
- No orders in the first 30 minutes (script warm-up) and nothing is held overnight: anything open at 15:55 ET is
  closed at market and logged as such.

## Pass / fail (evaluated by `journal.py stats`)
- Sample: at least 100 setups logged (taken or skipped) and at least 50 closed taken trades, all under the frozen parameters.
- Pass ("promising", never "proven"): average **net** R per closed taken trade >= +0.20.
- Fail: average net R below +0.20 at the sample size above, **or** cumulative drawdown of -10R from peak
  (all symbols combined, in closing order) at any point. Stop the test immediately.
- Rows logged after the Pine file changes are flagged and excluded.
- `stats` also prints results per symbol. They are informational only and are not a pass/fail input.

## Known limits
- The six symbols move together, so trades on the same day are not independent. The effective sample is smaller
  than the trade count, and one market regime over about 10 weeks is a thin test.
- The script does not detect absorption, big prints or delta. ETF volume is split across venues, so these
  confirmations are weaker evidence than on futures. This test checks whether the article's approach carries
  over to US ETFs and large caps at all.
- TradingView's volume for these symbols may be a partial feed. The profile matched SVP (same feed) but was not
  compared with consolidated volume.
- The 20-session frequency count reflects that period only; the rate may differ going forward.
- A result at this sample size is a reason to continue to Step 3, not a proven edge.
