#!/usr/bin/env python3
"""Monte Carlo odds of passing a prop-firm challenge with a given trading edge.

Part of claude-prop-firm-skills by Viprasol Tech Private Limited.

Each trade risks a fixed fraction of the INITIAL balance (how most challenge
traders size) and wins `reward` R with probability `win_rate`, otherwise loses
1 R. Trades are grouped into days; the run passes when the profit target is hit
(after the minimum number of trading days) and fails on a daily-loss or
max-loss breach, or when it runs out of days.

  python challenge_sim.py --win-rate 0.45 --reward 2 --risk 1 --target 10 --daily-loss 5 --max-loss 10
  python challenge_sim.py --win-rate 0.55 --reward 1 --risk 0.5 --trades-per-day 3 --max-days 60 --trailing
  python challenge_sim.py --self-test

All percentages are of the initial balance. This is a model, not a forecast:
real trades are not independent, edges decay and slippage exists. Use it to
compare risk settings, not to promise a pass rate.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    target: float = 10.0        # % profit to pass
    daily_loss: float = 5.0     # % of initial balance, measured from the day's starting balance
    max_loss: float = 10.0      # % of initial balance
    trailing: bool = False      # max loss trails the highest end-of-day balance, locks at the initial balance
    min_days: int = 0           # minimum trading days before a pass counts
    max_days: int = 0           # 0 = unlimited (capped at 1000 days)


@dataclass(frozen=True)
class Edge:
    win_rate: float
    reward: float               # R multiple of a win
    risk: float                 # % of initial balance risked per trade
    trades_per_day: int = 2


def run_once(edge: Edge, rules: Rules, rng: random.Random) -> tuple[str, int]:
    bal = 0.0          # P&L in % of initial balance
    peak = 0.0
    limit_days = rules.max_days or 1000
    for day in range(1, limit_days + 1):
        day_start = bal
        for _ in range(edge.trades_per_day):
            bal += edge.risk * edge.reward if rng.random() < edge.win_rate else -edge.risk
            if day_start - bal >= rules.daily_loss - 1e-12:
                return "daily_loss", day
            # trailing: the floor follows the end-of-day balance high and stops at the initial balance
            floor = min(peak - rules.max_loss, 0.0) if rules.trailing else -rules.max_loss
            if bal <= floor + 1e-12:
                return "max_loss", day
            if bal >= rules.target - 1e-12 and day >= rules.min_days:
                return "pass", day
        peak = max(peak, bal)
        if bal >= rules.target - 1e-12 and day >= rules.min_days:
            return "pass", day
    return "timeout", limit_days


def simulate(edge: Edge, rules: Rules, runs: int = 20000, seed: int = 7) -> dict:
    nums = (edge.win_rate, edge.reward, edge.risk, rules.target, rules.daily_loss, rules.max_loss)
    if not all(math.isfinite(x) for x in nums) or runs < 1:
        raise ValueError("inputs must be finite numbers and runs >= 1")
    if not 0 < edge.win_rate < 1 or edge.reward <= 0 or edge.risk <= 0 or edge.trades_per_day < 1:
        raise ValueError("win rate must be between 0 and 1; reward, risk and trades per day positive")
    if rules.target <= 0 or rules.daily_loss <= 0 or rules.max_loss <= 0:
        raise ValueError("target, daily loss and max loss must be positive")
    rng = random.Random(seed)
    counts = {"pass": 0, "daily_loss": 0, "max_loss": 0, "timeout": 0}
    pass_days = []
    for _ in range(runs):
        outcome, day = run_once(edge, rules, rng)
        counts[outcome] += 1
        if outcome == "pass":
            pass_days.append(day)
    p = counts["pass"] / runs
    se = math.sqrt(p * (1 - p) / runs)
    pass_days.sort()
    return {
        **{k: v / runs for k, v in counts.items()},
        "pass_ci95": (max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)),
        "median_days_to_pass": pass_days[len(pass_days) // 2] if pass_days else None,
        "expectancy_r": edge.win_rate * edge.reward - (1 - edge.win_rate),
        "losses_to_daily_limit": math.ceil(rules.daily_loss / edge.risk - 1e-9),
        "losses_to_max_limit": math.ceil(rules.max_loss / edge.risk - 1e-9),
    }


def _self_test() -> None:
    # A coin flip at 1:1 with symmetric target/limit: pass ~ 50% (gambler's ruin), no daily limit binding
    r = simulate(Edge(0.5, 1.0, 1.0, 1), Rules(target=10, daily_loss=50, max_loss=10), runs=20000)
    assert abs(r["pass"] - 0.5) < 0.02, r
    # Gambler's ruin with drift: p=0.6, 1:1, +5/-5 units -> (1-(q/p)^5)/(1-(q/p)^10)
    q_p = 0.4 / 0.6
    exact = (1 - q_p ** 5) / (1 - q_p ** 10)
    r = simulate(Edge(0.6, 1.0, 2.0, 1), Rules(target=10, daily_loss=50, max_loss=10), runs=40000)
    assert abs(r["pass"] - exact) < 0.015, (r["pass"], exact)
    # Tighter risk never lowers the pass rate for a positive edge here
    hi = simulate(Edge(0.45, 2.0, 2.0, 3), Rules(), runs=10000)["pass"]
    lo = simulate(Edge(0.45, 2.0, 0.5, 3), Rules(max_days=0), runs=10000)["pass"]
    assert lo > hi, (lo, hi)
    # Daily loss binds: 5 x 1% losses in a day breaches a 5% daily limit
    assert simulate(Edge(0.45, 2.0, 1.0, 3), Rules())["losses_to_daily_limit"] == 5
    # Trailing max loss can only fail more often than static
    s = simulate(Edge(0.5, 1.5, 1.0, 2), Rules(trailing=False), runs=10000)
    t = simulate(Edge(0.5, 1.5, 1.0, 2), Rules(trailing=True), runs=10000)
    assert t["pass"] < s["pass"] - 0.02, (t, s)
    # Minimum days delays passes
    m = simulate(Edge(0.6, 2.0, 2.0, 3), Rules(min_days=10), runs=5000)
    assert m["median_days_to_pass"] >= 10
    assert abs(sum(simulate(Edge(0.5, 1, 1, 1), Rules(max_days=5), runs=2000)[k] for k in ("pass", "daily_loss", "max_loss", "timeout")) - 1) < 1e-9
    for bad in (Edge(1.2, 1, 1), Edge(0.5, 0, 1), Edge(0.5, 1, 0)):
        try:
            simulate(bad, Rules(), runs=10)
        except ValueError:
            continue
        raise AssertionError(bad)
    print("challenge_sim self-test passed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monte Carlo prop-firm challenge pass probability")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--win-rate", type=float, help="0-1")
    ap.add_argument("--reward", type=float, help="Average win in R (risk multiples)")
    ap.add_argument("--risk", type=float, help="Risk per trade, %% of initial balance")
    ap.add_argument("--trades-per-day", type=int, default=2)
    ap.add_argument("--target", type=float, default=10.0, help="Profit target, %%")
    ap.add_argument("--daily-loss", type=float, default=5.0, help="Daily loss limit, %% of initial balance")
    ap.add_argument("--max-loss", type=float, default=10.0, help="Max loss, %% of initial balance")
    ap.add_argument("--trailing", action="store_true", help="Max loss trails the end-of-day balance high (locks at the initial balance)")
    ap.add_argument("--min-days", type=int, default=0)
    ap.add_argument("--max-days", type=int, default=0, help="0 = unlimited")
    ap.add_argument("--runs", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if a.win_rate is None or a.reward is None or a.risk is None:
        ap.print_help()
        return 2
    try:
        r = simulate(Edge(a.win_rate, a.reward, a.risk, a.trades_per_day),
                     Rules(a.target, a.daily_loss, a.max_loss, a.trailing, a.min_days, a.max_days), a.runs, a.seed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    lo, hi = r["pass_ci95"]
    print(f"expectancy           {r['expectancy_r']:+.2f} R per trade")
    print(f"pass                 {r['pass']:.1%}  (95% CI {lo:.1%} - {hi:.1%})")
    print(f"fail: daily loss     {r['daily_loss']:.1%}")
    print(f"fail: max loss       {r['max_loss']:.1%}")
    print(f"ran out of days      {r['timeout']:.1%}")
    print(f"median days to pass  {r['median_days_to_pass']}")
    print(f"losing trades to hit daily limit {r['losses_to_daily_limit']}, max limit {r['losses_to_max_limit']}")
    if r["expectancy_r"] <= 0:
        print("note: zero or negative expectancy - lower risk only delays failure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
