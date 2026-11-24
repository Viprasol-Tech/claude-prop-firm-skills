---
name: restricted-practices
description: Check a trading strategy, EA or bot against prop-firm restricted practices before it costs a funded account - news-trading windows by firm and account type (FTMO 2 minutes, Topstep 5 minutes, FundedNext 5 minutes with profit cut, The5ers 2 minutes), weekend and market-break holding, EA bans by account size or platform, HFT, latency and feed arbitrage, tick scalping and very short trades (FundedNext Quick Strike), hedging and opposite positions across accounts, copy trading, account management by third parties, request limits, and gap trading. Use when reviewing an EA or bot for a prop firm, choosing a firm for an automated strategy, or explaining a profit deduction or account closure.
---

# Restricted practices at prop firms

Drawdown limits are only half the rules. Firms also restrict **how** you
trade, and an EA can break those rules thousands of times a day. Rules as
published in November 2026; they differ by product and change often, so
check the firm's current page for the exact account type (sources in
`reference.md`). This skill helps you comply; it is not a guide to getting
around rules.

## News windows

| Firm / account | Window | What is restricted | Consequence |
|---|---|---|---|
| FTMO funded (FTMO Account) and Instant | 2 min before to 2 min after selected releases | any order execution on affected instruments, including SL/TP and pending fills | rule violation |
| FTMO Challenge, Verification, Swing | none | - | - |
| Topstep | 5 min before to 5 min after Tier 1 releases | no new opening positions in mini index and metals; micros capped | enforced by TopstepX |
| FundedNext (funded) | 5 min either side of high-impact news on correlated pairs | trades keep 40% of their profit | profit cut |
| The5ers High Stakes (evaluation and funded) | 2 min before to 2 min after high-impact news | opening orders | profit from the trade removed and not counted toward the target |
| FundingPips | varies by model (Zero: 10 min, no opening, closing or holding) | check the account type | - |

Code it as a calendar filter: load high-impact events (the firm usually
names its calendar source) with UTC times, map each to the affected
currencies or contracts, and block entries, pending-order fills and, where
required, open positions inside the window. Remember that a resting stop or
take-profit filling inside the window counts at FTMO.

## Holding rules

- FTMO: close positions before market breaks longer than 2 hours (including
  weekends) on accounts where the rule applies; Swing accounts are exempt.
  Check whether it applies in your phase.
- Topstep: flat by 3:10 PM CT every day; no overnight holding.
- The5ers futures: no weekend holding.
- Add a hard session-end close in the EA or bot, with a buffer before the
  deadline for slow fills.

## Automation and EA rules

| Firm | Rule |
|---|---|
| FTMO | EAs allowed; no more than 2,000 server requests a day; no "ultra-high-speed" tools or feed/price-delay exploits |
| FundedNext (CFD) | EAs not allowed on $50k+ accounts (including tools that only change SL, TP or size) and not on cTrader or Match-Trader |
| FundingPips | third-party EAs only as trade or risk managers; your own fully automated EA allowed if you can prove ownership |
| The5ers | EAs allowed; latency, tick-scalping and feed-exploiting systems banned |
| Topstep | bots through the TopstepX API (sim accounts only); HFT, VPS and VPN banned |
| Apex | bots, algorithms and HFT banned on all account types |

## Practices most firms ban

- **Latency or feed arbitrage** and exploiting delayed prices or simulator
  fills.
- **Tick scalping / very short holds**: FundedNext's Quick Strike rule keeps
  profit from trades closed within 30 seconds under 30% of total profit.
- **Opposite positions across accounts** (one account long, another short,
  at the same or another firm) and "account stacking".
- **Hedging to game consistency rules**, for example spreading one move's
  profit over several days.
- **Copy trading** from or to other people; copying between your own
  accounts is allowed at some firms (FTMO futures pages, FundedNext
  challenges) and banned at others.
- **Third-party account management**: someone else trading or running your
  account.
- **Gap trading** around major news or market closes (FTMO: within 2 hours
  of a close of 2 hours or more).

## EA review checklist for a prop account

- [ ] Firm and account type allow automation; EA ownership rules met.
- [ ] News filter matches this account type's window and scope (fills too).
- [ ] Session-end and weekend closes where required.
- [ ] Minimum holding time if the firm has a short-trade rule.
- [ ] No coordination with other accounts (no opposite positions, no copying
      unless allowed).
- [ ] Request rate bounded (modify on bar close, throttle retries).
- [ ] Daily and max-loss guard (`mt5-ea-guard`, `futures-bot-guard`).
- [ ] Consistency rule respected if the firm has one.
