---
name: mt5-ea-guard
description: Make a MetaTrader 5 Expert Advisor respect prop-firm limits on its own - an equity guard (daily loss from the balance or the higher of balance and equity at the firm's reset, static max loss, safety buffer) that flattens every position and pending order and locks trading until the next reset, persists across restarts, finds the firm's trading day from GMT with CE(S)T, EET/EEST or US Central daylight saving, throttles requests, and checks open risk before each order; plus MT5 time functions (TimeCurrent, TimeTradeServer, TimeGMT), equity vs. balance, deal commissions and swaps, and EA rules firms enforce (request limits, news windows, weekend holds). Includes a PropGuard.mqh template. Use when building or reviewing an EA for FTMO, FundedNext, The5ers, FundingPips or any funded MT5 account.
---

# MT5 EA guard for funded accounts

A strategy that is fine on a personal account fails a challenge in one bad
afternoon if nothing in the EA knows the firm's limits. Put the limits in
code. Template: `templates/PropGuard.mqh` (MIT); rules per firm in
`prop-rules-engine`. Not compiled here (no MetaEditor in CI): compile and
test on a demo account first.

## Using the template

```mq5
#include "PropGuard.mqh"
CPropGuard guard;

int OnInit()
{
   // FTMO 2-Step style: 100k, 5% daily from the midnight CE(S)T balance, 10% static, act 1% early
   if(!guard.Init(100000.0, 5.0, 10.0, false, FIRM_TZ_CET, 0, 0, 1.0)) return INIT_PARAMETERS_INCORRECT;
   // The5ers / FundingPips style: daily base = max(balance, equity) at the SERVER's midnight
   // if(!guard.Init(100000.0, 5.0, 10.0, true, FIRM_TZ_SERVER, 0, 0, 1.0)) return INIT_PARAMETERS_INCORRECT;
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}
void OnTimer() { guard.Check(); }
void OnTick()
{
   if(!guard.Check()) return;
   // worst case if every stop is hit from CURRENT prices: all open positions + the new order + costs
   double worst = WorstCaseLossMoney();       // your function; refuse orders without a stop
   if(!guard.CanOpen(worst)) return;
   // ... place the order
}
```

What it does:

- Computes the **day base** when a new firm trading day starts: the balance at
  the reset is rebuilt from deal history (balance now minus today's deals,
  deposits excluded), so an EA attached mid-day after a loss still gets the
  firm's floor. With `useMaxBase`, equity at the reset is only known if the
  EA was running at the reset; after a restart it uses the strictest value it
  has and says so in the log.
- Compares **equity** (floating P&L included) with the max floor first, then
  the daily floor, each minus a buffer; on a touch it closes all positions
  and deletes all pending orders on the account (every symbol and EA, on
  purpose), then refuses to trade until the next reset (daily) or ever (max).
  Locks are flushed to disk at once (`GlobalVariablesFlush`), keyed by server
  and login.
- `CanOpen()` refuses an order if the worst case (every stop hit from current
  prices, plus costs) would cross a floor.
- Retries a failed flatten with back-off (3 s doubling to 5 minutes), so a
  closed market cannot burn the firm's request limit.
- `Init()` rejects a buffer that is not smaller than each limit.

Trailing max-loss models (FTMO 1-Step and Instant, futures firms) need a
floor that moves; adapt `MaxFloor()` using the model in `prop-rules-engine`
and persist the peak in a global variable too.

## Time: the bug behind most guard failures

| Function | What it returns | Pitfall |
|---|---|---|
| `TimeCurrent()` | time of the last quote from the server | stops moving without ticks (weekend, quiet symbol); inside `OnTick` it is the tick time |
| `TimeTradeServer()` | the terminal's estimate of current server time | derived from the PC clock |
| `TimeGMT()` | UTC from the PC clock and its DST setting | wrong if the VPS clock is wrong: sync it with NTP |
| all three in the Strategy Tester | the same simulated time | reset logic cannot be fully tested in the tester |

The firm's day is not always the server's day: FTMO resets at midnight
CE(S)T, which FTMO says can differ from platform time; FundedNext, The5ers and
FundingPips reset at the server's midnight (GMT+2/+3); Topstep's day starts
5 PM CT. Use `FIRM_TZ_SERVER` when the firm says "server time" (many servers
switch daylight saving on US dates, so an EU-rule zone would be an hour off
for a few weeks a year), and `FIRM_TZ_CET` / `FIRM_TZ_US_CENTRAL` when the firm
names a zone. Those compute the firm's time from `TimeGMT()` with EU or US
rules, checked against the IANA tz database for 2024-2032.

## Money: what equity contains

- Use `AccountInfoDouble(ACCOUNT_EQUITY)` for limits, as firms do.
  FTMO defines equity as balance + open P/L ± swaps - commissions.
  How a broker books an entry commission (at once to balance, or on close)
  varies; log both values and compare with the firm's dashboard on day one.
- Closed P&L of a deal = `DEAL_PROFIT + DEAL_COMMISSION + DEAL_SWAP +
  DEAL_FEE`. Skip `DEAL_TYPE_BALANCE` (deposits, withdrawals, payouts) and
  `DEAL_TYPE_CREDIT`.
- `DEAL_TIME` is server time; convert before assigning a deal to a firm day.

## EA rules firms enforce (check your firm's page)

- **Request volume**: FTMO forbids an EA causing more than 2,000 server
  requests a day. Modify stops on bar close, not every tick; throttle
  retries.
- **News windows** on some account types (FTMO funded and Instant: no
  execution from 2 minutes before to 2 minutes after selected releases,
  including SL/TP fills; others differ): see `restricted-practices`.
- **Weekend and market breaks**: FTMO requires flat positions before breaks
  longer than 2 hours except on Swing accounts. Add a Friday close time.
- **Banned styles**: latency or feed arbitrage, tick scalping, opposite
  positions across accounts, third-party account management. Some firms
  cap EA use by account size (FundedNext: no EAs on $50k+ accounts) or by
  platform.
- **Third-party EAs**: some firms allow only trade or risk managers from
  third parties; your own EA may need proof of ownership.

## Review checklist

- [ ] Limits computed on equity in real time, from a persisted day base.
- [ ] Firm time zone and reset hour configured; VPS clock on NTP.
- [ ] Buffer before every limit; flatten closes positions and pending orders.
- [ ] Lock survives restarts; no trading after a lock until the reset.
- [ ] Open risk checked before each order, across all positions.
- [ ] Request rate bounded; no per-tick modify loops.
- [ ] News, weekend and Friday-close rules for this account type.
