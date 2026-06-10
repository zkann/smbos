# Roadmap

Working list, maintained as items ship. Shipped history lives in the git log.

## Next up (UX for non-technical owners)

1. **Morning digest.** A scheduled headless run that reads `pending/`, `runs.jsonl`, and trigger state, and sends one plain-language email or Slack message: what's waiting for approval, what automation cost this week, what failed and why in owner words. Implemented as an SOP with a cron trigger, so it dogfoods the trigger system.
2. **Plain-language pass.** Ban system vocabulary from every user-facing surface: the dashboard renders "every Monday at 8:57 AM" instead of `cron(57 8 * * 1)` (a humanizer already exists in `mcp_server.py`; reuse it), "ran on its schedule" instead of "source: cron", and friendly labels for overlay/variant badges. Add a protocol rule on the Code side: schedules, statuses, and failures are described in plain words; spec syntax is for files only.
3. **Plain-language failure reports.** Triggered-run errors land in `runs.jsonl` as raw API strings. Translate them where the owner looks (dashboard, digest) with one suggested action ("Monday's report didn't run because Claude wasn't logged in; open Claude Code once and it'll fix itself").
4. **Dashboard as action surface.** Approve/Discard buttons on parked runs in live mode (discard is safe in-browser; approve flips status for the next session/runner to execute), plus a per-SOP "Run now" button with the cost note.
5. **Guided first week.** A getting-going meter in the dashboard and at session start, driven from data already on disk ("8 SOPs installed, 1 has run; easiest next win: ..."). Bootstrap mode's missing second half.

## Later

- **Trigger-miss detection.** When a session realizes mid-task that a matching SOP existed but didn't fire, capture the phrase the user actually used and propose it as a trigger. (The protocol's implicit-feedback rule covers some of this conversationally; make it systematic.)
- **Remote MCP bridge.** The same seven MCP tools over authenticated HTTP so claude.ai web and mobile can reach the library; unlocks phone approvals. Local stdio covers Desktop today.
- **Dashboard direct editing.** Deliberately deferred: suggestions-only preserves the single propose/approve path. Revisit if dashboard suggestions see heavy real use.
- **More SmbOS modules beyond SOPs.** The "operating system" ambition: candidates include a lightweight ops journal and a contacts/commitments tracker, both file-based like SOPs.

## Principles for anything added here

Plain markdown, no lock-in. Diffs, not magic. Actions execute only where the full plugin runs. Plain words on every owner-facing surface.
