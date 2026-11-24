# Security policy

## Reporting a vulnerability

Please report security problems privately through
[GitHub security advisories](https://github.com/Viprasol-Tech/claude-prop-firm-skills/security/advisories/new)
or by email to [support@viprasol.com](mailto:support@viprasol.com). Do not open a public issue.
We aim to reply within 3 working days.

## Scope

- The bundled scripts (`prop_rules.py`, `challenge_sim.py`) read local files or
  arguments and make no network calls. `PropGuard.mqh` is an MQL5 template that
  closes positions when a limit is hit. A guard that fails to act, or acts on
  the wrong day or base, is in scope.
- Skill instructions that could lead an assistant to weaken account safety:
  missing or late loss limits, unbounded order retries, or advice to evade a
  firm's rules.

## Keep secrets out of chats

These skills never need your keys or funds. Never paste broker or exchange API keys,
account passwords, investor passwords or API tokens into an issue, pull request or
chat. Use synthetic data and sandbox keys. If a key has been
exposed, rotate it with your provider immediately.
