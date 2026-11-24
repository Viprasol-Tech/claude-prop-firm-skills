# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-24

### Added
- `prop-firm-guard` Claude Code plugin with 6 skills: `prop-rules-engine`,
  `challenge-planner`, `mt5-ea-guard`, `futures-bot-guard`,
  `restricted-practices`, `prop-journal`.
- `prop_rules.py`: replays an equity log against daily-loss bases, reset
  times and static, end-of-day, balance and intraday trailing max-loss models.
- `challenge_sim.py`: Monte Carlo pass probability under target, daily and
  max loss, minimum days and time limits, checked against gambler's ruin.
- `PropGuard.mqh`: MQL5 equity guard with persisted day base, locks,
  buffer, request throttling and EU/US daylight-saving firm days.
- Rules checked against FTMO, FundedNext, The5ers, FundingPips, Topstep and
  Apex help pages and the MQL5 docs in November 2026.
