---
name: prop-rules-engine
description: Encode prop-firm drawdown rules exactly the way each firm computes them - daily loss from the balance at the reset vs. the higher of balance and equity vs. the initial balance, the reset time and time zone (FTMO midnight CE(S)T, GMT+2/+3 server midnight, Topstep 5 PM CT), static vs. end-of-day trailing vs. balance-trailing vs. intraday equity-trailing max loss and where trailing locks, floating P&L, swaps and commissions, profit targets, minimum days and best-day/consistency rules for FTMO, FundedNext, The5ers, FundingPips, Topstep and Apex. Includes a tested checker that replays an equity log against a rule model. Use when building a risk guard, dashboard, journal or EA for a funded account, or when a trader's numbers disagree with the firm's breach notice.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/prop_rules.py *)
---

# Prop-firm rules engine

Firms publish rules in prose; code needs a model. Every rule below reduces
to a few choices: **what base**, **when the day starts**, **what is measured
(balance or equity)**, and **whether the floor moves**. Rules as published in
November 2026; firms change them often (see `reference.md`), so keep them
in a config file per firm, product and account phase.

## Replay a log against a rule model

```bash
python ${CLAUDE_SKILL_DIR}/scripts/prop_rules.py equity.csv --initial 100000 --daily 5% --daily-base day_balance --max 10% --reset 00:00 --tz Europe/Prague --target 10%
python ${CLAUDE_SKILL_DIR}/scripts/prop_rules.py equity.csv --initial 50000 --max 2000 --max-model trailing_eod --lock-at 50000 --reset 17:00 --tz America/Chicago --target 3000
python ${CLAUDE_SKILL_DIR}/scripts/prop_rules.py equity.csv --initial 100000 --max 10% --max-model trailing_eod --lock-at none --reset 00:00 --tz Europe/Prague
```

Input: `time,balance,equity[,cashflow]` rows, logged from the start of the
account and across each reset. Timestamps need a UTC offset, or pass
`--naive-tz` (MT5 writes server time without one). `cashflow` marks deposits
(+) and withdrawals or payouts (-) so they are not counted as P&L. The day
base is taken from the last row before the reset (with a warning when that
row is old). Trailing models need `--lock-at` (an amount or `none`). Output:
first breach, closest call to each limit, profit vs. target, trading days vs.
`--min-days` (days with a closed trade or an open position). Exit codes: 0 ok,
1 breach, 2 bad input. IANA zones need the tz database (`pip install tzdata`
on Windows); a fixed offset is wrong across daylight-saving changes.

## The building blocks

| Choice | Options | Notes |
|---|---|---|
| Daily base | `day_balance`: balance at the reset; `day_max`: higher of balance and equity at the reset; `initial` | a floating loss carried over midnight counts against the new day at most firms |
| Daily limit size | % of **initial** balance (most CFD firms) or a fixed amount | not % of the current balance |
| Measured value | **equity** (closed + floating, net of swaps and commissions) | closed-P&L-only checks miss most breaches |
| Day boundary | firm's reset time in the firm's time zone | the MT5 server clock can differ from it |
| Max loss | `static` (initial - limit); `trailing_eod` (highest end-of-day balance - limit); `trailing_balance` (highest balance as trades close); `trailing_intraday` (highest equity including open profit) | trailing floors usually stop at a lock level |
| Consistency | best day <= X% of total profit, on closed P&L per trading day | changes often; check before payouts |

## Firm models (November 2026, verify on the firm's site)

| Firm / product | Daily loss | Max loss | Other |
|---|---|---|---|
| FTMO 2-Step | 5% of initial, from the **balance at 00:00 CE(S)T** (`day_balance`) | 10% **static** | targets 10% then 5%; 4 trading days per phase |
| FTMO 1-Step | 3% of initial, same base | 10% below the highest midnight balance, **never locks**, resets after a reward (`trailing_eod --lock-at none`) | consistency: best day <= 50% of total profit (from 12 Oct 2026) |
| FTMO Instant | 3%, same base | trails the **balance** intraday (`trailing_balance --lock-at none`) | best day <= 30% |
| FundedNext Stellar 2-Step | 5% of initial; closed + floating incl. swaps, commissions, fees; reset 00:00 server time (GMT+2/+3) | 10% static (balance or equity) | targets 8% then 5%; 5 days per phase |
| The5ers High Stakes | 3-5% by plan, from the **higher of balance and equity** at 00:00 server time (`day_max`) | 8-10% static | 3 profitable days per step, each >= 0.5% |
| FundingPips 2-Step Standard | 3% or 5%, from the higher of the day's opening balance or equity (`day_max`) | 10% static, floating included | targets 8% then 5%; 3-day minimum on the 5% version |
| Topstep Trading Combine 50K | optional Daily Loss Limit (pauses until 5 PM CT, not a failure) | $2,000, trails the **end-of-day balance**, locks at the starting balance; monitored in real time including unrealised P&L (`trailing_eod --lock-at 50000`, reset 17:00 America/Chicago) | target $3,000; best day < 55% of target; flat by 3:10 PM CT |
| Apex EOD (rules from 1 Mar 2026) | daily loss limit pauses the session | trails the closing balance once a day at 4:59:59 PM ET; enforced intraday on Performance Accounts; Performance Accounts lock at start + $100 | choose EOD or Intraday at purchase; legacy accounts keep old rules |
| Apex Intraday | - | trails peak balance including unrealised gains, in real time (`trailing_intraday`) | lock level depends on account type and data feed |

The checker does not encode firm names on purpose: the same firm runs
different models per product and changes them. Map each account to a model
in your config, with the date you checked the rules page.

## Implementation rules

1. **Compute on equity in real time**, not on closed trades at the end of
   the day.
2. **Assign trading days in the firm's time zone** from UTC timestamps.
   FTMO's day is CE(S)T, FundedNext/The5ers/FundingPips use server midnight
   at GMT+2/+3, Topstep's day starts 5 PM CT.
3. **Persist the day base** at the reset (database row or MT5 global
   variable); recomputing it after a restart from the current balance is
   the classic bug.
4. **Trailing floors only go up**, and stop at the lock level when the firm
   has one.
5. **Stop before the line**: a guard flattening at the exact limit breaches
   on slippage. Use a buffer (for example 0.5-1% of initial).
6. Deposits, withdrawals and payouts are balance operations, not P&L;
   exclude them (MT5 `DEAL_TYPE_BALANCE`).
7. Keep a rules file per account with the source URL and check date, and
   re-check it monthly.
