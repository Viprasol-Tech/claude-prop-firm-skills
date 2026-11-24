#!/usr/bin/env python3
"""Check an equity history against prop-firm drawdown rules, the way the firm computes them.

Part of claude-prop-firm-skills by Viprasol Tech Private Limited.

Input: CSV with columns time, balance, equity[, cashflow] - one row per
snapshot (an EA can log every few seconds) from the START of the account.
`cashflow` is a deposit (+) or withdrawal/payout (-) booked at that row; it is
not P&L. Output: the first breach, the closest call for each rule, profit vs.
target and trading days vs. the minimum.

Rule models (pick the one your firm's rules page describes):
  daily base   day_balance       limit measured from the balance at the daily reset
               day_max           ... from the higher of balance and equity at the reset
               initial           ... from the initial balance
  max loss     static            floor = initial - limit
               trailing_eod      floor trails the highest end-of-day balance (or equity, --trail-on equity)
               trailing_balance  floor trails the highest balance as trades close, intraday
               trailing_intraday floor trails the highest equity seen (open profit included), in real time
  trailing floors stop rising at --lock-at (an amount, or "none"); required for trailing models.

The day base is the state at the reset: the last snapshot BEFORE the reset
(day 1 uses the initial balance). Log continuously across the reset, or the
tool warns that the base may be stale.

  python prop_rules.py equity.csv --initial 100000 --daily 5% --daily-base day_balance --max 10% --reset 00:00 --tz +01:00
  python prop_rules.py equity.csv --initial 50000 --max 2000 --max-model trailing_eod --lock-at 50000 --reset 17:00 --tz -06:00
  python prop_rules.py --self-test

Amounts: "5%" = percent of the initial balance, "2500" = account currency.
--tz takes a fixed UTC offset (+01:00) or an IANA zone (Europe/Prague) when
the tz database is available (on Windows: pip install tzdata). A fixed offset
is wrong across daylight-saving changes. Timestamps without an offset are
rejected unless --naive-tz says what they are (MT5 writes server time).
Exit codes: 0 ok, 1 breach, 2 bad input.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation

STALE_BASE = timedelta(minutes=15)


@dataclass(frozen=True)
class Rules:
    initial: Decimal
    daily: Decimal | None            # amount, already converted from %
    daily_base: str = "day_balance"  # day_balance | day_max | initial
    max_loss: Decimal | None = None
    max_model: str = "static"        # static | trailing_eod | trailing_balance | trailing_intraday
    trail_on: str = "balance"        # for trailing_eod: balance | equity
    lock_at: Decimal | None = None   # trailing floor stops rising here; None = never
    target: Decimal | None = None
    min_days: int = 0
    reset: time = time(0, 0)
    tz: tzinfo = timezone.utc


def dec(text: str, what: str, positive: bool = True) -> Decimal:
    try:
        v = Decimal(str(text).strip())
    except InvalidOperation:
        raise ValueError(f"bad {what}: {text!r}") from None
    if not v.is_finite() or (positive and v <= 0):
        raise ValueError(f"{what} must be a positive number: {text!r}")
    return v


def parse_amount(text: str, initial: Decimal) -> Decimal:
    t = text.strip()
    return initial * dec(t[:-1], "percent") / 100 if t.endswith("%") else dec(t, "amount")


def parse_tz(text: str) -> tzinfo:
    m = re.fullmatch(r"([+-])(\d\d):?(\d\d)", text.strip())
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
    if text.upper() in {"UTC", "Z"}:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(text)
    except Exception as exc:  # missing tz database (e.g. Windows without tzdata)
        raise ValueError(f"unknown time zone {text!r}: install the tz database (pip install tzdata), "
                         "or pass the UTC offset valid for the WHOLE log period") from exc


def trading_day(ts: datetime, rules: Rules) -> date:
    """The trading day a timestamp belongs to: days start at the reset time in the firm's time zone."""
    local = ts.astimezone(rules.tz)
    return (local - timedelta(hours=rules.reset.hour, minutes=rules.reset.minute)).date()


def reset_instant(day: date, rules: Rules) -> datetime:
    return datetime.combine(day, rules.reset).replace(tzinfo=rules.tz)


def evaluate(rows: list[tuple], rules: Rules) -> dict:
    """rows: (ts, balance, equity) or (ts, balance, equity, cashflow)."""
    if not rows:
        raise ValueError("no rows")
    rows = sorted(rows, key=lambda r: r[0])
    lock = rules.lock_at

    def capped(f: Decimal) -> Decimal:
        return f if lock is None else min(f, lock)

    warnings: list[str] = []
    cum_cash = Decimal(0)
    day = None
    day_base = rules.initial
    peak_eod = peak_eq = peak_bal = rules.initial
    prev = None                         # previous row, net of cash flows: (ts, bal, eq)
    floor = rules.initial - rules.max_loss if rules.max_loss is not None else None
    breach = None
    min_daily_room = min_max_room = None
    active_days: set[date] = set()
    for r in rows:
        ts = r[0]
        cum_cash += r[3] if len(r) > 3 and r[3] is not None else Decimal(0)
        bal, eq = r[1] - cum_cash, r[2] - cum_cash          # P&L view: cash flows removed
        d = trading_day(ts, rules)
        if d != day:
            if prev is not None:
                if rules.max_model == "trailing_eod":
                    peak_eod = max(peak_eod, prev[1] if rules.trail_on == "balance" else prev[2])
                state_bal, state_eq = prev[1], prev[2]
                if reset_instant(d, rules) - prev[0] > STALE_BASE:
                    warnings.append(f"{d}: last snapshot before the reset is at {prev[0].isoformat()}; "
                                    "the day base may be stale (log continuously across the reset)")
            else:
                state_bal = state_eq = rules.initial          # day 1: initial balance
            day = d
            day_base = {"day_balance": state_bal, "day_max": max(state_bal, state_eq),
                        "initial": rules.initial}[rules.daily_base]
        if prev is not None and (bal != prev[1] or eq != bal):
            active_days.add(d)
        elif prev is None and (bal != rules.initial or eq != bal):
            active_days.add(d)
        if rules.max_loss is not None:
            if rules.max_model == "trailing_intraday":
                peak_eq = max(peak_eq, eq)
                floor = capped(peak_eq - rules.max_loss)
            elif rules.max_model == "trailing_balance":
                peak_bal = max(peak_bal, bal)
                floor = capped(peak_bal - rules.max_loss)
            elif rules.max_model == "trailing_eod":
                floor = capped(peak_eod - rules.max_loss)
            else:
                floor = rules.initial - rules.max_loss
        if rules.daily is not None:
            room = eq - (day_base - rules.daily)
            if min_daily_room is None or room < min_daily_room[0]:
                min_daily_room = (room, ts)
            if room <= 0 and breach is None:
                breach = ("daily loss", ts, eq + cum_cash, day_base - rules.daily + cum_cash)
        if floor is not None:
            room = eq - floor
            if min_max_room is None or room < min_max_room[0]:
                min_max_room = (room, ts)
            if room <= 0 and breach is None:
                breach = ("max loss", ts, eq + cum_cash, floor + cum_cash)
        prev = (ts, bal, eq)
    profit = prev[1] - rules.initial
    return {
        "breach": breach,
        "min_daily_room": min_daily_room,
        "min_max_room": min_max_room,
        "profit": profit,
        "target_hit": rules.target is not None and profit >= rules.target,
        "trading_days": len(active_days),
        "min_days_met": len(active_days) >= rules.min_days,
        "final_floor": floor,
        "warnings": warnings,
    }


def load_csv(path: str, naive_tz: tzinfo | None = None) -> list[tuple]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), start=2):
            try:
                ts = datetime.fromisoformat(r["time"].strip().replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    if naive_tz is None:
                        raise ValueError("timestamp has no UTC offset (pass --naive-tz, e.g. the MT5 server's zone)")
                    ts = ts.replace(tzinfo=naive_tz)
                bal = dec(r["balance"], "balance", positive=False)
                eq = dec(r["equity"], "equity", positive=False)
                cash = dec(r["cashflow"], "cashflow", positive=False) if (r.get("cashflow") or "").strip() else None
            except (KeyError, ValueError) as exc:
                raise ValueError(f"line {i}: {exc}") from None
            out.append((ts, bal, eq, cash))
    return out


def _self_test() -> None:
    D = Decimal
    cet = timezone(timedelta(hours=1))

    def t(s: str) -> datetime:
        return datetime.fromisoformat(s)

    # The5ers/FundingPips-style: daily limit from the higher of balance and equity at the reset.
    r = Rules(D(100000), D(5000), "day_max", D(10000), "static", reset=time(0), tz=cet)
    rows = [
        (t("2026-11-23T22:59:00+00:00"), D(100000), D(103000)),   # 23:59 CET, open profit at the reset
        (t("2026-11-23T23:00:00+00:00"), D(100000), D(103000)),   # 00:00 CET new day: base = 103000
        (t("2026-11-24T09:00:00+00:00"), D(100000), D(98100)),    # -4900 from base: ok
        (t("2026-11-24T10:00:00+00:00"), D(100000), D(97999)),    # -5001: breach
    ]
    res = evaluate(rows, r)
    assert res["breach"] and res["breach"][0] == "daily loss" and res["breach"][3] == D(98000), res
    # FTMO-style: from the balance at midnight CE(S)T (balance 100000 at reset): no daily breach
    res = evaluate(rows, Rules(D(100000), D(5000), "day_balance", D(10000), reset=time(0), tz=cet))
    assert res["breach"] is None and res["min_daily_room"][0] == D(2999), res
    # Base is the state AT the reset, not the first row after it (logger down at midnight)
    rows = [(t("2026-11-23T22:58:00+00:00"), D(100000), D(103000)),
            (t("2026-11-24T08:00:00+00:00"), D(100000), D(98500)),
            (t("2026-11-24T09:00:00+00:00"), D(100000), D(97500))]
    res = evaluate(rows, r)
    assert res["breach"] and res["breach"][3] == D(98000), res
    # Reset boundary: 22:59 UTC belongs to the previous CET day
    assert trading_day(t("2026-11-23T22:59:00+00:00"), r).isoformat() == "2026-11-23"
    assert trading_day(t("2026-11-23T23:00:00+00:00"), r).isoformat() == "2026-11-24"
    # Futures-style end-of-day trailing: 50k account, 2000 trailing on EOD balance, locks at 50100, reset 17:00 CT
    ct = timezone(timedelta(hours=-6))
    fr = Rules(D(50000), None, max_loss=D(2000), max_model="trailing_eod", lock_at=D(50100), reset=time(17), tz=ct)
    rows = [
        (t("2026-11-23T15:00:00-06:00"), D(51000), D(51500)),   # day 1 close balance 51000
        (t("2026-11-23T18:00:00-06:00"), D(51000), D(49100)),   # day 2: floor 49000, ok
        (t("2026-11-24T16:00:00-06:00"), D(53000), D(53000)),   # day 2 close 53000
        (t("2026-11-24T18:00:00-06:00"), D(53000), D(50150)),   # day 3: floor min(51000, 50100) = 50100: ok
        (t("2026-11-24T19:00:00-06:00"), D(53000), D(50099)),   # breach at locked floor
    ]
    res = evaluate(rows, fr)
    assert res["breach"] and res["breach"][0] == "max loss" and res["breach"][3] == D(50100), res
    # FTMO 1-Step style: EOD trailing that never locks
    nr = Rules(D(100000), None, max_loss=D(10000), max_model="trailing_eod", lock_at=None, reset=time(0), tz=cet)
    rows = [(t("2026-11-23T12:00:00+01:00"), D(115000), D(115000)), (t("2026-11-24T12:00:00+01:00"), D(115000), D(104999))]
    res = evaluate(rows, nr)
    assert res["breach"] and res["breach"][3] == D(105000), res
    # Balance trailing (FTMO Instant style): open profit does not move the floor, closed profit does
    br = Rules(D(100000), None, max_loss=D(5000), max_model="trailing_balance", lock_at=None)
    rows = [(t("2026-11-24T10:00:00+00:00"), D(100000), D(108000)), (t("2026-11-24T10:01:00+00:00"), D(100000), D(95500)),
            (t("2026-11-24T11:00:00+00:00"), D(103000), D(103000)), (t("2026-11-24T11:01:00+00:00"), D(103000), D(97999))]
    res = evaluate(rows, br)
    assert res["breach"] and res["breach"][1] == rows[3][0] and res["breach"][3] == D(98000), res
    # Intraday trailing follows unrealised highs
    ir = Rules(D(50000), None, max_loss=D(2500), max_model="trailing_intraday", lock_at=D(50100), reset=time(17), tz=ct)
    rows = [(t("2026-11-23T10:00:00-06:00"), D(50000), D(51500)), (t("2026-11-23T10:05:00-06:00"), D(50000), D(49000))]
    res = evaluate(rows, ir)
    assert res["breach"] and res["breach"][3] == D(49000), res
    # Cash flows are not P&L: a payout is not a daily loss, a deposit does not hit the target
    cr = Rules(D(100000), D(5000), "day_balance", D(10000), target=D(10000), reset=time(0), tz=cet)
    rows = [(t("2026-11-24T10:00:00+01:00"), D(104000), D(104000), None),
            (t("2026-11-24T11:00:00+01:00"), D(98000), D(98000), D(-6000)),   # payout
            (t("2026-11-25T11:00:00+01:00"), D(108000), D(108000), D(10000))]  # deposit
    res = evaluate(rows, cr)
    assert res["breach"] is None and res["profit"] == D(4000) and not res["target_hit"], res
    # Trading days: days with balance changes or open positions, not days with snapshots
    rows = [(t(f"2026-11-{d}T10:00:00+01:00"), D(100000), D(100000)) for d in (20, 21, 22, 23)]
    rows.append((t("2026-11-24T10:00:00+01:00"), D(100500), D(100500)))
    res = evaluate(rows, Rules(D(100000), None, min_days=4, reset=time(0), tz=cet))
    assert res["trading_days"] == 1 and not res["min_days_met"], res
    # Stale base warning when the log has a hole over the reset
    res = evaluate([(t("2026-11-23T12:00:00+01:00"), D(100000), D(100000)),
                    (t("2026-11-24T09:00:00+01:00"), D(100000), D(100000))], Rules(D(100000), D(5000), tz=cet))
    assert res["warnings"], res
    assert parse_amount("5%", D(100000)) == D(5000) and parse_amount("2500", D(1)) == D(2500)
    for bad in ("-1", "abc", "0%", "nan"):
        try:
            parse_amount(bad, D(100))
        except ValueError:
            continue
        raise AssertionError(bad)
    assert parse_tz("+05:30").utcoffset(None) == timedelta(hours=5, minutes=30)
    print("prop_rules self-test passed")


def build_rules(a) -> Rules:
    initial = dec(a.initial, "--initial")
    trailing = a.max_model != "static"
    if trailing and a.lock_at is None:
        raise ValueError('trailing models need --lock-at (an amount, or "none" if the floor never stops)')
    lock = None if (not trailing or a.lock_at == "none") else dec(a.lock_at, "--lock-at")
    hh, mm = (int(x) for x in a.reset.split(":"))
    return Rules(
        initial,
        parse_amount(a.daily, initial) if a.daily else None,
        a.daily_base,
        parse_amount(a.max_loss, initial) if a.max_loss else None,
        a.max_model, a.trail_on, lock,
        parse_amount(a.target, initial) if a.target else None,
        a.min_days, time(hh, mm), parse_tz(a.tz))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check an equity history against prop-firm drawdown rules")
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--initial")
    ap.add_argument("--daily", help='Daily loss limit, "5%%" of initial or an amount')
    ap.add_argument("--daily-base", choices=["day_balance", "day_max", "initial"], default="day_balance")
    ap.add_argument("--max", dest="max_loss", help='Max loss, "10%%" of initial or an amount')
    ap.add_argument("--max-model", choices=["static", "trailing_eod", "trailing_balance", "trailing_intraday"], default="static")
    ap.add_argument("--trail-on", choices=["balance", "equity"], default="balance")
    ap.add_argument("--lock-at", help='Trailing floor stops rising here: an amount, or "none" (required for trailing)')
    ap.add_argument("--target", help='Profit target, "10%%" or an amount')
    ap.add_argument("--min-days", type=int, default=0, help="Minimum trading days")
    ap.add_argument("--reset", default="00:00", help="Daily reset time HH:MM in --tz")
    ap.add_argument("--tz", default="UTC", help="Firm time zone: IANA name, or a UTC offset like +01:00")
    ap.add_argument("--naive-tz", help="Time zone of timestamps that have no offset (e.g. the MT5 server zone)")
    a = ap.parse_args(argv)
    if a.self_test:
        _self_test()
        return 0
    if not a.csv or a.initial is None:
        ap.print_help()
        return 2
    try:
        rules = build_rules(a)
        res = evaluate(load_csv(a.csv, parse_tz(a.naive_tz) if a.naive_tz else None), rules)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for w in res["warnings"]:
        print("warning:", w)
    if res["breach"]:
        kind, ts, eq, lvl = res["breach"]
        print(f"BREACH  {kind} at {ts.isoformat()}: equity {eq} <= limit {lvl}")
    else:
        print("no breach")
    if res["min_daily_room"]:
        print(f"closest to daily limit: {res['min_daily_room'][0]} left at {res['min_daily_room'][1].isoformat()}")
    if res["min_max_room"]:
        print(f"closest to max limit:   {res['min_max_room'][0]} left at {res['min_max_room'][1].isoformat()}")
    line = f"profit {res['profit']} (cash flows excluded), {res['trading_days']} trading day(s)"
    if rules.target is not None:
        line += f", target {'hit' if res['target_hit'] else 'not hit'}"
    if rules.min_days:
        line += f", minimum days {'met' if res['min_days_met'] else 'not met'}"
    print(line)
    return 1 if res["breach"] else 0


if __name__ == "__main__":
    sys.exit(main())
