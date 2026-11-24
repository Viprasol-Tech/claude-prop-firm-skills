---
name: challenge-planner
description: Plan a prop-firm challenge with numbers instead of hope - Monte Carlo pass probability from win rate, reward-to-risk and risk per trade under the firm's profit target, daily loss limit, max loss (static or trailing), minimum days and time limit; how many losing trades each limit allows; why higher risk lowers the pass rate even with an edge; and a risk-per-trade plan that leaves room for slippage and floating losses. Includes a tested simulator. Use when someone asks how much to risk per trade on an FTMO, FundedNext, The5ers, Topstep or Apex challenge, whether their strategy can pass, or how to size an EA or bot for a funded account.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/challenge_sim.py *)
---

# Challenge planner

A challenge is a race between a profit target and two loss limits. The
question is never "can this strategy make 10%?" but "what is the chance it
makes 10% before it loses 5% in a day or 10% overall?". Engineering and
statistics, not trading advice.

## Simulate it

```bash
python ${CLAUDE_SKILL_DIR}/scripts/challenge_sim.py --win-rate 0.45 --reward 2 --risk 1 --target 10 --daily-loss 5 --max-loss 10
python ${CLAUDE_SKILL_DIR}/scripts/challenge_sim.py --win-rate 0.45 --reward 2 --risk 2.5 --target 10 --daily-loss 5 --max-loss 10   # same edge, more risk
python ${CLAUDE_SKILL_DIR}/scripts/challenge_sim.py --win-rate 0.55 --reward 1 --risk 0.5 --trades-per-day 4 --target 6 --max-loss 4 --trailing
```

Output: pass rate with a 95% confidence interval, failure split (daily loss,
max loss, ran out of days), median days to pass, and how many consecutive
losers each limit allows. The self-test checks the simulator against the
exact gambler's-ruin formula.

With the first two lines above, the same +0.35 R edge passes about 97% of
the time at 1% risk and about 46% at 2.5% risk. Risk per trade is the main
lever a trader controls.

## Inputs that matter

- **Win rate and average R from real trades**, not from a backtest's best
  run. Use at least 100 trades; with fewer, run the simulator at the low end
  of the win rate's confidence interval.
- **Risk as a share of the initial balance.** Most challenges measure limits
  in percent of the initial balance, so a fixed-percent-of-initial position
  size keeps the arithmetic simple.
- **Trades per day** decides whether the daily limit can bind: with 1% risk
  and two trades a day a 5% daily limit cannot be hit by closed trades alone.
- **The firm's exact rule model**: daily loss from balance or from the higher
  of balance and equity at the reset, static or trailing max loss, minimum
  days. See `prop-rules-engine`.

## Rules of thumb the simulator usually confirms

- Keep **losing trades to the daily limit at 4 or more** and to the max limit
  at 8 or more. The simulator prints both numbers.
- A trailing max loss (common on futures evaluations) fails more often than a
  static one at the same size: profits raise the floor (`--trailing` models an
  end-of-day trail that locks at the initial balance; in the third example it
  cuts the pass rate from about 81% to 65%).
- Negative or zero expectancy cannot be fixed by sizing; lower risk only makes
  the failure slower.
- Leave a buffer for what the model ignores: floating losses count towards
  most daily limits, slippage on stops, swaps and commissions, and correlated
  positions (three USD pairs are one trade).

## Turning the plan into code

- Size every order from the stop distance so one loss equals the chosen risk
  (`position-sizing` in claude-trading-skills; tick value per lot, not pip
  guesses).
- Enforce the plan in the EA or bot, not only in the trader's head: daily
  loss guard, max open risk, max trades per day (`mt5-ea-guard`,
  `futures-bot-guard`).
- Log every day's start balance, equity low and closed P&L so the real
  results can replace the assumptions (`prop-journal`).

## Model limits

Trades are assumed independent with fixed win and loss sizes, and daily
limits are checked on closed trades. Streaky strategies, news gaps and
floating drawdown make real results worse. Compare settings with it; do not
promise anyone a pass rate.
