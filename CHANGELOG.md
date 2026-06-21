# Changelog

## 0.40.0 (2026-06-21)

- The dashboard now has a System view, so you can see at a glance that everything is running. The parked tab carries a health dot (green when your scheduled jobs are on time, amber when one looks stalled), and a System panel lists each job, when it last ran, and what is flowing through (open job routes, the eval signal, waiting tasks). Before this there was no window into the background jobs, so a silently stalled inbox check could go unnoticed. A job opts into the health readout by declaring a `liveness_file` in its spec.

## 0.39.0 (2026-06-19)

- You can now clear a task off your plate without picking it up. When you've already handled a waiting task out-of-band (done by hand, or handled somewhere else), each plate row has a quiet checkmark to mark it done and a dismiss control (not mine, or won't do) on the right, brightening on hover. Before this, the only way to check a task off was to launch a full Claude session and mark it done there, so the plate stays a mirror you can trust without that detour.

## 0.38.0 (2026-06-19)

- "Hand to Claude" now opens each task in its own clean working folder (under `~/smbos-tasks`) instead of your whole home directory, so the picked-up session is focused on that one task. Combined with the priming from the last release, a task like a coding challenge opens in a fresh folder, finds the file it names (often in `~/Downloads`), and works there. A task that already has a folder of its own still opens in that folder.

## 0.37.0 (2026-06-19)

- When you hand a task to Claude from the sidebar, the new session now gets the task's "why this is here" line, not just the title, plus a nudge to find any file the task names (a spec, a download) and work from there even if the session opened in a different folder. This helps most on high-context tasks like a coding challenge, where the work lives in a local file the dashboard can't point at directly.

## 0.36.0 (2026-06-19)

- New: an "Opaque background" toggle in the sidebar's Settings. The docked panel normally uses a frosted, see-through background, which can be hard to read over a busy or light desktop. Turn this on to make it a solid dark background instead. It is a per-device display preference (remembered on this Mac) and only appears in the docked sidebar.

## 0.35.0 (2026-06-19)

- A round of sidebar polish from a design review. The buttons on In-flight, prepared, and procedure rows are now the same comfortable size as the rest (they were a little small and easy to mis-tap). A task's Open and Hand-to-Claude buttons now sit under its title instead of floating off to the right, so your eye stays on the tasks. Titles all line up on one left edge. The "N due" count reads as a clearer amber alert. Keyboard focus outlines and disabled-button styling are now consistent across every control.

## 0.34.0 (2026-06-19)

- The sidebar is easier to use. To open a task's details, click its title (the whole title is the target) instead of the tiny caret that was hard to hit and easy to miss. The caret stays as a small marker showing which tasks have more to see. The per-task buttons (Open, Hand to Claude) are a little larger too, so they are easier to hit. Everything on your plate stays as dense and quick to read as before, with bigger targets and clearer affordances.

## 0.33.0 (2026-06-19)

- A task's details can now include links. When a task carries a piece of context that lives at a link (a spec, a requirements doc, the email thread), it shows in the task's details as a clickable link in the app's accent color instead of plain text. This is the first step toward richer context for tasks that need more than a one-line reason, like a coding challenge with a spec and a deadline.

## 0.32.0 (2026-06-19)

- The "why this is here" line now shows directly on a task in the sidebar, under its title, instead of only inside the task's details. It's trimmed to one line (the full text is still in the details when you open them), so you can tell what a task is and why it's on your plate at a glance. On a task with a deadline the line turns amber, matching the due date and the row's amber edge, so an urgent reason can't hide.

## 0.31.0 (2026-06-19)

- A task on your plate can now show a short "why this is here" line. When the source that created a task explains why it landed on your plate, that reason leads the task's details, so you can tell what a task is at a glance without opening the source. Tasks with details now open from the toggle on the row even when the only thing inside is that reason, and tasks that carry no reason look exactly as before. This is the first step toward a fuller task view, and it also quietly records which workflow produced each task for later use.

## 0.30.0 (2026-06-17)

- The dashboard now knows when a picked-up session has stopped. An in-flight task used to always show a green "live" dot, even if you closed its window or it crashed without reporting; now the dashboard tracks the session's process, so a task whose session is gone turns amber and reads "stalled", with Put back as the highlighted action to return it to your plate. A task that's genuinely still being worked stays live. This is the awareness half of the in-flight work; the manual Put back / Done / Dismiss controls and the session's own reporting (0.29.0) still apply.

## 0.29.1 (2026-06-16)

- The dashboard watchdog now bounds its `launchctl` calls with a timeout, so a hung `launchctl` can't leave the every-few-minutes check stuck. A timed-out or failed call is treated as "did nothing this run" and the next run retries; nothing about when the watchdog restarts the dashboard changes.

## 0.29.0 (2026-06-16)

- Picked-up tasks now clear themselves from "in flight" when the session is done. When you pick up a task, the Claude session it opens is told to record the outcome as its last step: finished, should-not-be-done, or put it back on your plate. So the dashboard reflects what happened on its own, instead of leaving the task in flight until you resolve it by hand. The manual Put back / Done / Dismiss buttons stay as the backstop, and a late report can't override a task you already resolved yourself. (Still on the list: the dashboard noticing on its own when a session dies without reporting, so a dropped task surfaces as stalled rather than showing a live dot.)

## 0.28.1 (2026-06-16)

- The always-on dashboard install now sets up a small cron watchdog that keeps it running. On some macOS versions launchd does not honor a LaunchAgent's auto-start and restart, so the dashboard would not come back after a crash or a reboot. The watchdog checks the dashboard's configured port every few minutes and starts it again when it's down. `cutover_dashboard install` adds it; `uninstall` removes it. (This release also catches plugin.json up to the 0.26–0.28 changelog entries.)

## 0.28.0 (2026-06-16)

- In-flight tasks can be recovered from the dashboard. Picking up a task moves it to "in flight" and opens a Claude session; if that session was closed or died before the work was recorded, the task used to be stuck there with no way out. Now each in-flight item has Put back (returns it to your plate), Done, and Dismiss, so nothing is ever trapped. The next step is the dashboard knowing on its own when a session finishes, rather than relying on you to resolve it.

## 0.27.0 (2026-06-16)

- The dashboard has a compact layout for the menu-bar side panel. At sidebar width it keeps what needs you (your plate and pending approvals) at the top, under a sticky header that shows the waiting / in flight / coming up counts, and tucks the rest (in flight, coming up, recent runs, procedures, settings) behind a tap so the plate is never pushed below the fold. The full-width browser dashboard is unchanged; the panel loads the compact layout on its own.
- The dashboard also reflows cleanly at narrow widths in general (the side panel and small browser windows): the wide page gutters shrink and the settings controls go full-width instead of overflowing.

## 0.26.0 (2026-06-16)

- New: a macOS menu-bar app for the dashboard. A small SmbOS icon sits in the menu bar showing how many items are waiting for you (a monogram that fills in when there is work and stays quiet at zero, with a warning mark if the dashboard is not running). Its menu breaks down what is on your plate, in flight, and coming up, and opens the dashboard, restarts it, or quits. It runs at login alongside the dashboard service and talks to it over the existing local URL, so there is nothing new to configure.
- The menu-bar app can dock the dashboard as a side panel next to whatever you are working in. By default it stays out of the way: a thin handle on the right edge slides the dashboard in when you reach the edge and hides it again when you move away, so it never permanently blocks an app. "Dock as sidebar" parks it open and resizes the window beside it so nothing is covered (this needs Accessibility permission, which it asks for the first time, and falls back to the peek panel until granted). Install with `tray_app.py install`, remove with `tray_app.py uninstall`.
- The menu-bar app is macOS-only and carries its own dependencies (rumps and a few pyobjc frameworks, installed into the dashboard's virtualenv); the rest of SmbOS stays stdlib-only on the system Python. It installs as a small SmbOS.app wrapper so macOS shows "SmbOS" in notifications and the menu. (The one-time Accessibility prompt for the dock feature still shows the Python interpreter's name; naming it there needs Developer ID signing, tracked in #54.)

## 0.25.1 (2026-06-16)

- Dashboard notifications open the dashboard when clicked, instead of launching Script Editor. macOS attributes `osascript` notifications to Script Editor and gives them no click target, so when `terminal-notifier` is present the app posts through it with the dashboard URL as the click action. The dashboard install adds `terminal-notifier` via Homebrew when it's available; without it, notifications still appear through the previous path.

## 0.25.0 (2026-06-16)

- The live dashboard is now a single-page app served by a small local web service, replacing the generated-HTML daemon. It updates in real time as runs start and finish, with no refresh, and adds per-procedure controls: run or queue a SOP, prepare a draft, or pick up an interactive one. Alongside are panels for parked results waiting on you, what's coming up, recent runs, and settings. The URL and token are unchanged.
- Installing the always-on dashboard is now `cutover_dashboard.py <sop-dir> install`. The first run builds a small virtualenv for the app and its web bundle, then takes over the same LaunchAgent and port (8765). The switch health-checks the new server and rolls back to the previous one if it does not answer, so the port is never left dark. `serve_dashboard.py install` now points you at this command.
- This dashboard app is the one part of SmbOS that carries dependencies (fastapi/uvicorn and a built web bundle). Everything else, the SOP runner, importer, MCP server, and shared library, stays stdlib-only and runs on the system Python.

## 0.24.0 (2026-06-15)

- The live dashboard can run as an always-on background service with a URL that never changes. `serve_dashboard.py <sop-dir> install` registers a macOS LaunchAgent that starts at login, restarts itself if it stops, and auto-restarts when the plugin updates, bound to a fixed port (8765 by default, configurable) with a token persisted 0600. Bookmark the URL once and it keeps working across sessions, reboots, and updates. `url` prints it, `rotate` mints a new token (invalidating the old URL), `uninstall` removes the service. A manual launch reuses the running one (found via the deterministic URL or a recorded actual port) instead of starting a second, and clears its record on clean shutdown. macOS only for the service; the per-session server is unchanged elsewhere.

## 0.23.0 (2026-06-15)

- The dashboard footer now has a grouped Settings section. Beyond the launch posture (added in 0.22.0), you can set the monthly automation budget (pairs with the spend meter on Today), which terminal the launch buttons open, and a daily-summary time plus a notify toggle. All persist to triggers.json with the file mode preserved. The daily-summary time installs a scheduled entry on this Mac (the first dashboard feature that touches your crontab; it writes a single tagged line, replaces rather than duplicates, and removing the time removes the line).

## 0.22.0 (2026-06-14)

- The dashboard footer now has a "When I open Claude for a task" control to set how much a launched session asks before acting: ask before everything, ask before running things (the default), or don't ask and just run it. The riskiest choice carries a plain-words caution, the change saves immediately, and it applies to the next launch. Previously this was only settable from the command line.

## 0.21.0 (2026-06-14)

- SOPs can declare a canonical `folder:` (e.g. `folder: ~/clients/acme`). Queued tasks and launches for that SOP route there regardless of where the dashboard was opened, instead of inheriting the dashboard's launch folder. Fixes project-pinned SOPs getting tagged for whatever folder happened to be open; an explicit "any folder" queue choice still wins, and SOPs without the field keep the launch-folder behavior.

## 0.20.1 (2026-06-12)

- The content fingerprint now covers the background-run permission fields (`deliverable:`, `research_domains:`, `research_reads:`) as well as the steps. Before this, editing a stamped procedure's web-domain list outside the normal save flow kept its stamp, quietly widening what a background run could reach; now any such edit reads as unrecorded changes and background runs refuse until you review it. Found while dogfooding the first real background run. Re-stamp your library once after updating: `python3 scripts/sop_version.py stamp --all`.

## 0.20.0 (2026-06-12)

- Background-first: "Do it without me" is the primary verb on every runnable SOP. Prepare mode runs any SOP (drafts included) inside a harness-enforced capability cage: settings-source isolation, fetch only stamped `research_domains:`, reads only the library plus stamped `research_reads:` (empty scratch cwd makes read allow-listing real), writes only to pending/, no shell/search/MCP, secret-path deny belt. Gate matrix: prepare skips draft status only; personalize slots, unrecorded changes, missing inputs, and budget still refuse free; one run per SOP at a time via stale-safe pid lockfiles. Every run ends in a parked artifact (deliverable named, partial flagged, empty results are honest results; producing nothing is an error that notifies and shows under needs-attention). Discarding a result asks "what was off?" and writes it into the SOP's notes; approving a prepared result counts as a draft's first real run. New `scripts/canary_prepare.py` live-proves the cage (12 checks against a real model) and pins the verified CLI version; the runner warns on drift. A research SOP dry-ran to an approvable artifact under the cage (about $0.40).

## 0.19.0 (2026-06-10)

- Version integrity: SOPs carry a content fingerprint (sha256 of the procedure body; notes and changelog excluded). Edits that skip the save flow show up as "unrecorded changes": flagged on the dashboard with the version pill and a reconcile hint, refused (free) by unattended runs at all three gate layers, surfaced by the session hook with a reconciliation offer, and marked in Claude Desktop. New `sop_version.py`: `check`, `stamp`, and `bump --note`, which replaces five hand edits (version, changelog line, fingerprint, trusted-to-active demotion, clean-run reset) with one command. Missing fingerprints are quiet; existing libraries adopt via `stamp --all` or naturally through edits and promotions.

## 0.18.0 (2026-06-10)

- Command Center theme: shadcn zinc-dark tokens and component recipes (pill tabs, soft badges, outline/primary buttons, dark dialog, progress bar, focus rings) hand-ported to plain CSS, zero dependencies kept; fused with signal-green accents, monospace micro-labels and figures, and a glowing live dot. WCAG AA verified on every text/surface pair; full state matrix screenshot-verified.
- Design audit round 2 (post-theme): keyboard access for procedure cards, parked-approval items, and cross-SOP links; disabled buttons stay legible everywhere; truthful spend-bar track; all surface colors tokenized (no hex outside :root); radius and spacing scales converged; primary button promoted from location-based selector to .btn-primary; inline styles in generated markup replaced with classes. 15 atomic fixes, each screenshot-verified.
- Dashboard source split into `index.html` + `style.css` + `app.js`; the Python generator inlines them, so the output stays one self-contained file. app.js render functions are named 1:1 for future React components; React itself is pinned to the remote-bridge milestone (see ROADMAP).

## 0.17.2 (2026-06-10)

- Design audit pass (B+ to A-): action buttons reach a real click size (30px desktop, 44px touch), body text to 16px with a 12px microcopy floor, the footer shows `~/sops` instead of the absolute home path, and motion respects `prefers-reduced-motion`. DESIGN.md locks in the extracted design system, including why the system font stack is intentional.

## 0.17.1 (2026-06-10)

- Launch buttons open YOUR terminal: iTerm2 is natively supported alongside Terminal.app, auto-detected from the session that started the dashboard (`TERM_PROGRAM`), with a `terminal` config override in triggers.json. Field-found: the author uses iTerm2 and the hardcoded Terminal.app would have opened the wrong app on the first click.

## 0.17.0 (2026-06-10)

- The dashboard can open Claude for you. No more reading a folder name off the screen and typing it into a terminal: "Start in Claude" on a plate item opens a Terminal window already in the right folder with the task as Claude's first prompt; a draft's dialog leads with "Do it with Claude now" (the first trigger phrase becomes the opening words); approving a parked run offers "Do it now in Claude"; SOP files get an "open in editor" link. The browser sends only identifiers; folders and prompts are derived server-side from your own files. macOS only (AppleScript); the first click may show a one-time permission prompt ("Python wants to control Terminal").

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
