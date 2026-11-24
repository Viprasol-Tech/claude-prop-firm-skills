# Contributing

Thanks for helping traders and EA developers stay inside prop-firm rules. Fixes, new skills, better
checklists and corrections are all welcome.

## Ways to help

- **Fix a fact.** Prop firms change their rules often (limits, news windows, EA policies, trailing locks). If a rule, limit
  or header is out of date, open a PR with a link to the official source.
- **Improve a skill.** Each skill is a folder in `plugins/prop-firm-guard/skills/`
  with a `SKILL.md` (YAML frontmatter `name` + `description`, then instructions).
- **Add a skill.** Same layout. Keep `SKILL.md` under 500 lines; put long
  reference material in a separate file linked from it.
- **Improve the scripts** in `prop-rules-engine/scripts` and `challenge-planner/scripts`, or the `mt5-ea-guard` template.
  They must stay standard-library only and keep their `--self-test` passing.

## Before you open a PR

```bash
python tests/validate_repo.py
python plugins/prop-firm-guard/skills/prop-rules-engine/scripts/prop_rules.py --self-test
python plugins/prop-firm-guard/skills/challenge-planner/scripts/challenge_sim.py --self-test
```

Code samples must run as written and use sandbox or paper accounts only; never
real API keys, access tokens, webhook secrets or client IDs.

## Ground rules

- Accuracy over volume: cite official docs for platform facts.
- Regulatory content is engineering guidance, not legal or tax advice; cite the firm's own rules page and the date you checked it. Never add ways to get around a firm's rules.
- Never include real API keys, account numbers or personal data.
