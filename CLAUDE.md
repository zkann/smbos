# CLAUDE.md

SmbOS is a Claude Code plugin: an SOP manager for small-business owners. Plain-markdown SOPs in `~/sops`, a SessionStart hook that injects the protocol, stdlib-only Python scripts (no dependencies), a single-file vanilla-JS dashboard template, and a hand-rolled MCP stdio server.

Working rules for this repo:

- Run `python3 -m pytest tests/ -q` before committing; CI runs it on Python 3.9 and 3.12 (3.9 = the macOS system interpreter Claude Desktop uses).
- Zero runtime dependencies is a product property. Stdlib only in `scripts/`; no frameworks in the dashboard template.
- Owner-facing copy uses plain words: no cron syntax, no raw errors, no em dashes (house style). Shared vocabulary: "waiting for you", "on your plate", "in flight", "coming up".
- Dashboard changes need a screenshot check for every interactive state, not just DOM assertions (an invisible-disabled-button bug taught this).
- Shared helpers live in `scripts/smbos_lib.py`; do not re-implement frontmatter parsing or directory resolution.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
