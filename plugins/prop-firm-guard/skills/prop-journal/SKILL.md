---
name: prop-journal
description: Build a rule-aware trading journal for funded and challenge accounts - log the numbers firms judge you on (day-start balance and equity at the firm's reset time, intraday equity low, closed P&L with commissions and swaps, best-day share of profit, trading days, open risk), turn MT5, cTrader, NinjaTrader or Tradovate exports into per-day rule headroom, consistency and payout-eligibility reports, and spot rule drift before a breach. Use when someone wants to track a prop account, explain why a firm says they breached when their own stats say otherwise, check a consistency rule before requesting a payout, or build a dashboard for several funded accounts.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/../prop-rules-engine/scripts/prop_rules.py *)
---

# Rule-aware prop journal

Most "but I didn't breach!" disputes come from measuring a different number
than the firm: closed P&L instead of equity, local midnight instead of the
firm's reset, balance instead of the higher of balance and equity.
A prop journal records the firm's numbers.

## What to record

| Field | When | Why |
|---|---|---|
| Balance and equity at the firm's daily reset | every reset | base of the daily loss limit |
| Lowest equity of the day, with time | continuously (EA or bot logs it) | the daily limit is tested on equity, not closed P&L, at most firms |
| Highest equity / end-of-day balance | continuously / at reset | trailing max-loss floors move with these |
| Closed P&L per trade including commission, swap and fees | each deal | net numbers count; gross hides costs |
| Open risk (sum of stop-loss distances x size) | each order | how much one bad minute can cost |
| News events traded through | each trade | restricted windows on some account types (`restricted-practices`) |
| Platform, account id, firm, phase | static | rules differ by firm, account type and phase |

On MT5, log `AccountInfoDouble(ACCOUNT_BALANCE)` and `ACCOUNT_EQUITY` to a CSV
from `OnTimer()` every few seconds, including across the daily reset
(`time,balance,equity,cashflow`: ISO 8601 with an offset, and cashflow for
deposits, withdrawals and payouts). That file is exactly the input of the
rules checker.

## Check the history against the rules

```bash
python ${CLAUDE_SKILL_DIR}/../prop-rules-engine/scripts/prop_rules.py equity.csv --initial 100000 --daily 5% --daily-base day_balance --max 10% --reset 00:00 --tz Europe/Prague --target 10%
```

It prints the first breach (if any), the closest call to each limit and the
profit against the target, using the firm's reset time and base.

## Reports worth building

- **Daily headroom**: for each trading day, the lowest equity minus the daily
  floor. A trader who gets within 0.5% of the floor three days a week is one
  gap away from failing.
- **Consistency**: best day's profit as a share of total profit. Several
  firms cap it for payouts or for passing; compute it on the firm's
  definition (closed P&L per trading day, after costs).
- **Payout readiness**: profit above the payout threshold, minimum trading
  days met, consistency met, no open violations.
- **Cost drag**: commissions and swaps as a share of gross profit.
- **Multi-account view**: one row per account with phase, headroom and days
  left; never sum accounts with different rules.

## Data hygiene

- Store times in UTC with the source offset; convert to the firm's time zone
  only to assign trading days. A broker server at UTC+2/+3 and a firm resetting
  at midnight CE(S)T are an hour apart.
- Reconcile the journal with the firm's dashboard weekly; when they differ,
  the firm's number decides the account, so find out which rule model or
  timestamp you got wrong.
- Keep raw exports (deals, not only positions) so a later rule change can be
  re-run on old data.
