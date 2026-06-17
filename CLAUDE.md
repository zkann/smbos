# CLAUDE.md

SmbOS is a Claude Code plugin: an SOP manager for small-business owners. Plain-markdown SOPs in `~/sops`, a SessionStart hook that injects the protocol, stdlib-only Python scripts (the live-mirror dashboard app is the one dependency-bearing exception), a single-file vanilla-JS dashboard template, and a hand-rolled MCP stdio server.

Working rules for this repo:

- Run `python3 -m pytest tests/ -q` before committing; CI's `test` job runs it on Python 3.9 and 3.12 (3.9 = the macOS system interpreter Claude Desktop uses). The FastAPI dashboard app's tests need its deps, so they `importorskip` under that job and run under the separate `test-app` job (`pip install -r requirements-dev.txt`); run them locally with a venv.
- Stdlib-only, zero runtime dependencies, for everything EXCEPT two macOS-only, dependency-bearing components: the live-mirror dashboard app (`scripts/dashboard_app.py`, fastapi/uvicorn) and the menu-bar tray (`scripts/tray_app.py`, rumps + pyobjc), both per `requirements.txt` and both running under the dashboard's `.venv`. The legacy daemon (`serve_dashboard.py`), the MCP server, `run_sop.py`, the importer, and `smbos_lib.py` stay stdlib-only and must keep running on the system Python 3.9. The tray's pure logic is import-guarded so its tests run stdlib-only on 3.9 (rumps absent); only the running app needs the venv. (The blanket zero-dependency property was deliberately dropped 2026-06-15 for the dashboard rewrite; see the gstack design doc.)
- Owner-facing copy uses plain words: no cron syntax, no raw errors, no em dashes (house style). Shared vocabulary: "waiting for you", "on your plate", "in flight", "coming up".
- Dashboard changes need a screenshot check for every interactive state, not just DOM assertions (an invisible-disabled-button bug taught this).
- Before any UI/UX change, state the job-to-be-done and weigh 2-3 design options (chrome cost, discoverability, dead-ends, how each frames the relationship) before building. Don't default to the first idea; prefer making an existing on-screen referent clickable over adding new chrome, and never strand the user in one-way navigation.
- Shared helpers live in `scripts/smbos_lib.py`; do not re-implement frontmatter parsing or directory resolution.
- This is a public repo. Examples in docs, code, tests, CHANGELOG, and commit/PR text stay generic (client/invoice/proposal/onboarding processes; `~/clients/acme` for a project folder). Never mirror a real user's private workflow, clients, employer, or local file paths.

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
