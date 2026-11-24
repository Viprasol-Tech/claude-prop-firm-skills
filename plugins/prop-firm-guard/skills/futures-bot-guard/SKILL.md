---
name: futures-bot-guard
description: Keep a futures trading bot or strategy inside funded-account rules on Topstep, Apex and similar evaluations - trailing max loss on end-of-day balance vs. intraday peak (including open profit) and where it locks, daily loss limits that pause rather than fail, contract caps per account size, the trading day (5 PM CT start, Topstep flat by 3:10 PM CT, Apex 4:59 PM ET recalculation), consistency rules for passing and payouts, news-window contract limits, and which firms allow automation at all (TopstepX API sim-only, Apex bans bots on funded accounts). Use when writing or reviewing a NinjaTrader, Tradovate, Rithmic or TopstepX bot, a risk overlay for a futures evaluation, or when a trailing drawdown breach does not make sense.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/../prop-rules-engine/scripts/prop_rules.py *)
---

# Futures bot guard

Futures evaluations mostly use **trailing** max loss: profits raise the floor.
A bot that knows only "max loss $2,000" breaches without ever being down
$2,000 from its start. Rules as published in November 2026; verify on the
firm's help centre before coding a value (see `reference.md`).

## Before writing a bot: is automation allowed?

| Firm | Automation |
|---|---|
| Topstep | bots via the TopstepX API are allowed, but the API is sim-only (Combine and Express Funded, not Live Funded); HFT, VPS and VPN use are banned; TopstepX is the only platform |
| Apex Trader Funding | bots, algorithms, fully automated systems and HFT are banned on all account types (evaluations included); copying only across your own accounts with orders placed manually |
| The5ers futures programmes | HFT, algorithmic trading and hedging are banned |

Read the current terms for your firm and account type. If automation is not
allowed, a **risk overlay** that only watches the account and alerts the
trader is usually fine; one that places or flattens orders is automated
trading, so get the firm's written approval first.

## Drawdown models

| Model | Floor | Example |
|---|---|---|
| End-of-day trailing (Topstep Combine, Apex EOD) | highest end-of-day balance - limit, never down, locks at a level | Topstep 50K: $2,000 below the highest EOD balance, locks at the starting balance; monitored in real time including unrealised P&L |
| Intraday trailing (Apex Intraday) | highest balance including **open profit** - limit, in real time | a trade that runs +$1,500 then closes at +$200 has moved the floor up by $1,500 |
| Static | initial - limit | some "static" products |

Where the trail stops differs by product and even by data feed (Apex
Performance Accounts lock at start + $100; for evaluations, Apex pages
disagree on the lock level by feed, so treat it as unverified and read your
dashboard). Put the lock in config.

Replay a fills/equity log against a model:

```bash
python ${CLAUDE_SKILL_DIR}/../prop-rules-engine/scripts/prop_rules.py equity.csv --initial 50000 --max 2000 --max-model trailing_eod --lock-at 50000 --reset 17:00 --tz America/Chicago
python ${CLAUDE_SKILL_DIR}/../prop-rules-engine/scripts/prop_rules.py equity.csv --initial 50000 --max 2500 --max-model trailing_intraday --lock-at 50100 --reset 17:00 --tz America/Chicago
```

## Guard logic for a bot

```text
on every fill and every price update:
    equity      = balance + open P&L (with fees)
    peak        = max(peak, equity)            # intraday model
    floor       = min(peak - limit, lock)      # or EOD peak for EOD models
    if equity - buffer <= floor:  flatten, cancel working orders, stop for the day
    if day_pnl <= -daily_limit:   flatten, stop until the next session (5 PM CT)
before every order:
    contracts after fill <= cap for this account size (Topstep 50K: 5 minis or 50 micros)
    worst case (all stops hit) stays above floor and daily limit
    not inside a news window for restricted contracts
    not after the session cut-off (Topstep: flat by 3:10 PM CT)
at session close:
    record EOD balance, update the EOD peak, persist both
```

- **Persist the peak and the EOD balance** (database or file); a restart
  that forgets the peak puts the floor in the wrong place.
- **Size from the floor, not the start**: when the floor is $600 away, a
  2-contract stop of $400 each is already a breach.
- With intraday trailing, a **big open winner moves the floor** even if it
  is never realised. Take partial profits or tighten stops deliberately.
- Daily loss limits on Topstep (optional) and Apex pause trading until the
  next session; they are not failures, but a bot must stop placing orders.

## Session and news rules

- Topstep's day runs 5:00 PM to 3:10 PM CT, all positions must be flat by
  3:10 PM CT, and the best day locks at 3:10 PM. Apex recalculates EOD
  drawdown at 4:59:59 PM ET.
- Topstep: from 5 minutes before to 5 minutes after Tier 1 releases, no new
  opening positions in mini index and metals contracts and capped micros;
  TopstepX enforces it, and brackets that reduce a position still work.
- Use an economic calendar feed with release times in UTC and block entries
  inside each firm's window; flatten before the window if the rules require
  it for your account type.

## Consistency

- Topstep Combine: the best day must be under 55% of the profit target, or
  the target rises.
- Apex payouts: no single day of 50% or more of profit since the last payout.
- A bot that makes most of its money on one trend day passes the drawdown
  but fails consistency: size consistently every day and check the best-day
  share before requesting a payout.
