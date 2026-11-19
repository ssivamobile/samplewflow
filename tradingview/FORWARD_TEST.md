# Forward test: KOF levels + Model 1 screener on QQQ

Pre-registered 2026-11-19, before any trade was logged. Changing anything below after the first
logged trade starts a new test (re-freeze, new row set). The numbers marked *default* were chosen by
Claude on the user's instruction "use your defaults"; they are not from the article.

## Decisions (Step 0)
| Item | Value | Source |
|---|---|---|
| Instrument | QQQ only (SPY deferred: the two move together, so it would not give independent evidence) | default |
| Chart | TradingView, 5-minute (validated); 2-3 minute not yet validated | default |
| Session | RTH 09:30-16:00 ET; chart set to ETH so overnight levels exist | article / default |
| Opening range | 5 minutes (09:30-09:35) | user |
| Overnight levels | 16:00-09:29 ET (after-hours + pre-market) | default |
| Value area | 70%, two-row expansion from POC, volume from 1-minute bars | validated against TradingView SVP |
| Bin size | 4 ticks = 0.04 | validated against SVP on QQQ |
| Confluence / touch tolerance | 0.01% of price (about 0.07 on QQQ) | default |
| Candidate window / warm-up / min R to TP2 / max per day | 09:30-12:30 / 30 min / 2.0 / 3 | script defaults |
| Stop / targets | beyond sweep extreme + 0.5 x 21-bar range; TP1 = (VAH+VAL)/2, TP2 = opposite edge; stop to breakeven after TP1 | article / script |
| Costs | 0.02 per share round trip (spread + commission + slippage) | default assumption |
| Simulator | TradingView paper trading (nothing live) | default |

## Validation behind these choices (QQQ, Pine minus TradingView SVP, price units)
| Session | VAH | VAL | POC |
|---|---|---|---|
| Nov 13 | -0.02 | -0.10 | -0.06 |
| Nov 16 | 0.00 | -0.04 | +0.04 |
| Nov 17 | +0.05 | -0.03 | +0.37 |
| Nov 18 | -0.01 | -0.05 | -0.05 |

POC is the least stable level. MNQ was tested too and scattered 0-3 points against SVP, which is
one reason the futures setup was dropped.

## What counts as a setup
Every Model 1 candidate the screener raises, and every setup the trader notices by eye. Log it the
moment it appears, **taken or skipped**, with `journal.py add`. A skipped setup needs a reason.
Day type is judged live, before the outcome. Absorption, big trade and delta are confirmed by eye
(the script does not detect them).

## Execution rules (added 2026-11-19 on the user's instruction, before any trade)
- **Paper only.** Orders go through TradingView **Paper Trading** and nowhere else. Before each order the
  Trade panel must read "Paper Trading". No real broker, no other account, ever. If the panel shows anything
  else, no order is placed.
- **Take every mechanical candidate.** A Model 1 alert from the frozen script, inside the 09:30-12:30 window,
  with max 3 per day and R to TP2 >= 2.0 (script filters), is taken. The only reasons to skip are mechanical
  (outside window, daily limit, paper account unavailable, data delayed or stale). Skips are logged with a reason.
- **Confirmations are recorded, not used as a filter.** Absorption / big trade / delta are judged by eye from the
  footprint and logged (`yes` / `no` / `unknown`). `journal.py stats` then compares confirmed vs not confirmed.
  This keeps discretion out of entries until a numeric definition of each exists.
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
- Sample: at least 100 setups logged and at least 50 closed taken trades, all under the frozen parameters.
- Pass ("promising", never "proven"): average **net** R per closed taken trade >= +0.20.
- Fail: average net R below +0.20 at the sample size above, **or** cumulative drawdown of -10R from peak at any point (stop the test immediately).
- Rows logged after the Pine file changes are flagged and excluded.
- At 2-3 setups a day, 100 setups takes roughly 7 weeks, not 2-4. Plan for that.

## Known limits
- The script does not detect absorption, big prints or delta. ETF volume is split across venues,
  so these confirmations are weaker evidence than on futures. This test checks whether the
  article's approach carries over to an ETF at all.
- TradingView's NASDAQ:QQQ volume may be a partial feed. The profile shape matched SVP (same feed)
  but was not compared with consolidated volume.
- One symbol and a few weeks is one market regime.
- A result at this sample size is a reason to continue to Step 3, not a proven edge.
