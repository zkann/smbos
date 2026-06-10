# Changelog

## 0.16.0 (2026-06-10)

- Today-first dashboard: two tabs. Today leads with Waiting for you (inline approve/discard, reassuring empty state), Needs attention (translated failures), In flight, On your plate (queued tasks now visible on the dashboard, with their folder), Coming up (humanized schedules + a spend bar against the monthly allowance), and the getting-going meter. Procedures holds the sorted grid (trusted/active first, then by recency) with a status legend.
- Connection clarity: a header chip shows Live (with the launch folder) or Snapshot (with when it was taken); a heartbeat detects a dead live server and shows a what-to-do banner instead of failing silently; live pages auto-refresh when idle.
- One vocabulary everywhere: Waiting for you / On your plate / In flight / Coming up across dashboard, digest, and the session protocol. Cards drop version numbers, file paths, and counters in favor of "used 9 times, last yesterday"; SOP ids render as titles; relative dates throughout; queue buttons say "Put it on my plate".

## 0.15.0 (2026-06-10)

- Shared `scripts/smbos_lib.py`: one canonical implementation of directory resolution, frontmatter parsing, SOP iteration, and run-log reading; all six scripts refactored onto it (frontmatter parsing previously existed in five places and had already drifted once).
- Test suite: 46 pytest cases covering the humanizer, the runner's free gates (draft, missing inputs, budget), trigger registry and crontab generation, work-item lifecycle, digest sections, dashboard data (including the no-raw-cron-anywhere assertion), live-server endpoints with traversal guards, the MCP server over real JSON-RPC, and session-hook routing by project.
- CI: pytest on Python 3.9 (the macOS system interpreter Claude Desktop uses) and 3.12, hook syntax check, manifest validation, gitleaks.
- This file.

## 0.14.x (2026-06-10)

- Work-in-progress tracker: one markdown file per in-flight multi-stage item (stages, current stage, blocked/active/done, running log) via `work.py` and `/sop-work`; stage board on the dashboard, "In flight" digest section, project-aware session-start surfacing. Deliberately not a Linear replacement.
- Queue scope: queued tasks name their target folder in the confirmation, and a this-folder vs any-folder choice appears when the dashboard was opened from a project.

## 0.13.0 (2026-06-10)

- Project-aware queue routing: queued tasks carry the folder the dashboard was launched from; sessions offer tasks for their own folder (or unscoped ones) and point elsewhere for the rest.

## 0.12.0 (2026-06-10)

- Queue for next interactive session: the third run option, for work that needs a human mid-task. Dashboard button writes a `queue/` handoff; the next session offers to start it (which is also how drafts get verified); digest lists them under "On your plate".

## 0.11.x (2026-06-09 to 06-10)

- Owner-provided run inputs (`--inputs`, standing inputs per trigger, dashboard inputs box).
- Free input gate: `run_inputs:` frontmatter blocks unattended runs before any model spawns, at all three layers (button disabled, server reject, runner refusal at $0).
- Run-button states made visible; run-box copy rewritten as a "Tell it:" checklist; billing language corrected to "plan allowance" (the dollar figures track usage, not separate charges); drafts explain why they can't run in the background.

## 0.9.0 / 0.10.0 (2026-06-10)

- Token-free daily digest (DIGEST.md, macOS notification, optional Slack webhook) with plain-language failure translation.
- Plain-words pass: schedules render as "every Monday at 8:57 AM" everywhere; raw spec syntax stays in files.
- Dashboard actions: approve/discard on parked runs, run-now per SOP; getting-going meter.

## 0.8.0 (2026-06-10)

- MCP server (stdlib stdio JSON-RPC, no SDK): the SOP library in Claude Desktop chat. Seven tools; chat surfaces read, suggest, capture drafts, and record decisions; actions execute only where the full plugin runs. `/sop-connect` wires Desktop config safely.

## 0.7.0 (2026-06-10)

- Triggers: frontmatter `on:` specs, a registry (created disabled), headless runner via `claude -p` with cost logging, monthly budget guard, approval parking to `pending/`, payload-as-data hygiene, `/sop-triggers`.

## 0.5.0 / 0.6.0 (2026-06-09)

- Composition: `[[sop:id]]` sub-runs, `needs:`/`next:` chains, review audits for broken refs.
- Context layers: `## Variants` keyed by detectable conditions, project `./sops` overlays with `extends:`, corrections routed universal vs project-specific.

## 0.2.0 to 0.4.0 (2026-06-09)

- Cold start: 14-SOP starter library with business-type packs, draft/active/trusted maturity driven by clean runs, bootstrap mode, `/sop-import` (docs, interview, session-history mining).
- Visual dashboard (self-contained HTML, zero deps) with suggestion capture in static and live modes.

## 0.1.0 (2026-06-09)

- Initial SOP manager: plain-markdown SOPs with trigger phrases and a "My way" section, SessionStart protocol injection, capture/run/update/review commands, git-friendly, archive-never-delete.
