# SmbOS

An operating system for your small business, built on Claude Code.

The first module is an SOP manager. It turns the way YOU do recurring tasks into living documents that your AI follows, instead of doing everything its own default way.

## The problem

If you run a small business, you wear many hats: invoicing, content, client onboarding, weekly reporting, vendor wrangling. AI assistants can do most of these tasks, but they do them their way. You correct the same things every time: the tone, the format, the step you always do first, the thing you never send without reviewing. Those corrections evaporate when the session ends.

SmbOS makes the corrections permanent. Each recurring task gets a Standard Operating Procedure: a plain markdown file that records the steps, your preferences, and the places where you want to approve before anything goes out. Claude reads the SOP before doing the task, follows it, and proposes updates when reality disagrees with the document.

## How it works

**Start warm, not cold.** You don't begin with an empty library. `/sop-init` asks what kind of business you run and installs a starter pack: pre-built draft SOPs for the usual suspects (invoicing, lead follow-up, client onboarding, weekly numbers, support replies). `/sop-import` converts process docs you already have (Notion pages, checklists, an old handbook), interviews you ("explain it like you're training a new hire"), or mines your past Claude Code sessions for tasks you've done repeatedly. Until the library has five active SOPs, Claude is in bootstrap mode: it offers to capture an SOP after every repeatable task and names the gaps it notices ("second invoice this week, no SOP").

**Capture.** Do a task once with Claude, correcting as you go. Then `/sop-new` distills the conversation, corrections included, into an SOP. You approve it; it gets saved and indexed. Claude will also offer to capture an SOP on its own after it completes a repeatable task that has no SOP yet.

**Earn trust.** Every SOP has a maturity status. `draft` means unverified: starter-pack and imported SOPs begin here, with `[personalize]` slots Claude fills in by asking you on the first real run. One completed run makes it `active`. Three clean runs in a row (no corrections, no deviations) make it `trusted`. Any edit sends it back to active to re-earn trust. Drafts are cheap on purpose; the run loop is what hardens them.

**Match.** Every session starts with the SOP index loaded into context (via a SessionStart hook). When you ask for something that matches an SOP's trigger phrases, Claude reads the full SOP and follows it. You can also invoke one explicitly with `/sop-run`.

**Run.** Claude works the steps in order, defers to the "My way" section over its own defaults, and stops at every step marked **[APPROVAL]**. It tells you which SOP and version it is running, so nothing is hidden.

**Learn.** After each run, Claude updates usage metadata and, if anything deviated (a step skipped, a correction you made, a tool that misbehaved), proposes a specific edit as a before/after diff. Nothing changes without your approval. Every change bumps the version and gets a dated changelog line. Implicit signals count too: re-asking in different words, editing the output afterward, skipping a step. Those become trigger improvements and "My way" entries.

**Organize.** `/sop-list` shows the library with health flags. `/sop-review` is the monthly audit: stale SOPs whose triggers never fire, drifted SOPs that need a rewrite, overlapping SOPs to merge, and recurring tasks that still have no SOP.

## Principles

- **Plain markdown.** SOPs are files you can open, edit, and grep. No database, no server, no lock-in. Edit one by hand and the system picks it up.
- **Diffs, not magic.** The AI never silently rewrites your procedures. Every change is proposed, approved, versioned, and logged.
- **Your way wins.** An SOP's "My way" section overrides the AI's defaults even when the AI disagrees. If it thinks a rule is wrong, it says so and asks.
- **Git-friendly.** The SOP directory can be a git repo, so the full history of how your operations evolved is one `git log` away.
- **Archive, never delete.** Retired SOPs move to `archive/`. Your operational history is part of the product.

## Install

```
/plugin marketplace add zkann/smbos        # or a local path to this repo
/plugin install smbos@smbos
```

Then in any Claude Code session:

```
/sop-init
```

This creates your SOP directory (default `~/sops`, since business workflows follow you across projects; override with the `SOP_DIR` environment variable or a `./sops` directory in a workspace).

## Commands

You don't need to memorize these. The session protocol handles matching, capturing, and updating conversationally; "save this as an SOP" and "show me my SOPs" work fine. The commands are shortcuts.

| Command | What it does |
|---|---|
| `/sop-init` | Create the SOP directory and seed a starter pack for your business type |
| `/sop-new` | Capture a task as a new SOP, from the current conversation or a description |
| `/sop-import` | Convert existing docs, a brain-dump interview, or past session history into draft SOPs |
| `/sop-run <name>` | Execute a task by its SOP, with approval gates and deviation tracking |
| `/sop-update <name>` | Apply feedback to an SOP as a reviewed diff |
| `/sop-list` | Show the library with status, usage, and health flags |
| `/sop-review` | Monthly audit: stale, drifted, overlapping, missing, and never-run SOPs |
| `/sop-dashboard` | Open a visual dashboard of the library in your browser |
| `/sop-triggers` | Schedules, event triggers, budget, and automation cost reports |
| `/sop-connect` | Connect the library to Claude Desktop via MCP (no terminal there) |

## Claude Desktop (MCP)

The terminal is optional. `/sop-connect` wires a small MCP server (stdlib Python, same files, zero dependencies) into Claude Desktop chat, and from there your SOPs work in plain conversation: Claude checks the library before business tasks and follows your "My way" automatically, you capture new SOPs by describing how you do something, corrections become suggestions the next Code session folds in, and the approval queue is reviewable ("what's waiting for me?" then approve or discard). Cowork sessions on the same machine typically inherit the server too, though Anthropic doesn't officially support local MCP there yet.

The security split is deliberate: chat surfaces can read, suggest, capture drafts, and record decisions, but actions execute only where the full plugin runs. Approving in Desktop records the decision; the next Claude Code session (or scheduled run) executes it and confirms.

Scope honestly stated: this is local stdio MCP, so it reaches Claude Desktop on the machine where your SOPs live. claude.ai web and mobile only support remote (HTTP) connectors; a hosted bridge for phone approvals is on the roadmap, not in the box.

## Triggers and automation

SOPs can run themselves. Declare intent in frontmatter (`on: cron(57 8 * * 1)` for schedules, `on: linear.issue.created[label=bug]` for events), and `/sop-triggers` manages the rest: a registry in `triggers.json` where every trigger is created disabled and enabled explicitly, crontab lines or cloud routines for schedules, and generated n8n recipes for event webhooks.

Unattended runs are guarded four ways:

- **Maturity gate.** The runner refuses `draft` SOPs; only ones that survived a real human run go unattended.
- **Approval parking.** A triggered run executes up to the first **[APPROVAL]** step or externally visible action, then writes everything it prepared to `pending/` and stops. Your next session opens with "2 triggered runs awaiting approval", and the dashboard shows them; nothing sends, posts, or pays without you.
- **Budget guard.** Every run logs its cost to `runs.jsonl` (headless runs bill against your plan's separate agent credit). Set `monthly_budget_usd` once and the runner refuses to start runs past it. `/sop-triggers costs` gives spend by SOP versus budget.
- **Payload hygiene.** Event payloads (a Linear ticket body, a Slack message) are saved to disk and handled as data; the bridge maps event to SOP id itself, and payload content never chooses the SOP or adds instructions.

## The dashboard

For anyone who would rather look than read a terminal: `/sop-dashboard` (or just "show me my SOP dashboard") generates a single HTML file from your SOP directory and opens it in the browser. Cards grouped by category with status badges, run counts, and trigger phrases; a "needs attention" list for drafts that never ran, stale SOPs, and pending revision notes; search across everything; click any card for the full SOP with its changelog.

Every SOP has a "Suggest a change" box. In the default snapshot mode it copies a ready-made request you paste into Claude Code. In live mode (`/sop-dashboard --live`, a localhost-only server with a per-run token, stdlib Python, still zero dependencies) the suggestion saves straight into that SOP's "Notes for next revision", and the next Claude session opens by offering to turn pending suggestions into edits. The page re-reads your files on refresh in live mode.

Either way, restructuring an SOP stays with the propose/approve diff flow; the dashboard captures intent, it does not rewrite procedures. Nothing leaves the machine: the snapshot makes no network requests, and the live server binds 127.0.0.1 only.

## SOPs compose

Real workflows are rarely one SOP. Three relation types keep them small and chained instead of monolithic:

- A step containing `[[sop:meeting-follow-up]]` executes that SOP inline as a sub-run, with its own approval gates, usage tracking, and learning loop. (Obsidian users get clickable wiki-links for free; the dashboard renders them as links too.)
- `needs: find-jobs` in frontmatter says this SOP consumes another's output. If you ask to submit an application and there's no job in hand, Claude offers to run the finding step first.
- `next: submit-job-application` names what typically follows; when a run completes, Claude offers the next link in the chain, once.

`/sop-review` audits composition health: references to missing SOPs, loops, and step blocks duplicated across SOPs that should be extracted into a shared sub-SOP.

## One task, many projects

The same task often varies by project: TypeScript repos check tsc and vitest where Python repos check ruff and pytest, and one client's repo has its own review rules. Two mechanisms cover this without duplicating SOPs:

- **Variants**, for toolchain-sized forks. One SOP grows a `## Variants` section where each variant names a detectable condition ("TypeScript projects (package.json present)"). Claude detects which applies before running and says so; if it can't tell, it asks once.
- **Overlays**, for whole-project personalities. A project's `./sops/` directory is a second layer over your home library (`~/sops`). An overlay file with `extends: <home-id>` carries only the sections that differ; they replace the base's, except "My way", which appends, so project rules add to your universal rules rather than erasing them.

Resolution precedence: what you explicitly asked for, then the project overlay, then the variant condition, then asking. Every run announces how it resolved.

The learning loop respects the layers: when you correct something mid-run, Claude asks whether it's universal or specific to this project, and routes the edit to the base SOP or the overlay. That one question is what keeps project quirks from leaking into every other project's behavior. `/sop-review` audits the rest: orphaned overlays, near-duplicates that should be base plus overlay, and variants that have drifted identical.

## Anatomy of an SOP

See [examples/weekly-metrics-report.md](examples/weekly-metrics-report.md) for a complete example. The short version:

```markdown
---
id: send-invoice            # filename and reference handle
triggers: invoice X, bill   # phrases you actually say
version: 3                  # bumped on every approved change
content_hash: 3f9a1c2b4d6e  # fingerprint of the steps; edits that skip the save flow get noticed
runs: 12                    # usage tracking feeds the review audit
status: trusted             # draft -> active (1 real run) -> trusted (3 clean runs)
---
## Steps        (concrete, executable by a session with no memory of today)
## My way       (your preferences that override AI defaults: the point of the SOP)
## Edge cases   (known exceptions)
## Changelog    (what changed, when, and why)
```

The "My way" section is the heart. If it is empty, you did not need an SOP; the AI's default behavior was already fine.

**"Do it without me."** Any SOP, including drafts, can prepare work in the background: the run happens inside a safety cage (it can only fetch web domains and read files the stamped SOP declares, write only its result artifact, and has no shell, search, or external tools; enforced by the harness's permission system with settings isolation, not by prompt text) and always ends by parking a result under "waiting for you", with a notification. Approving a prepared result counts as the draft's first real run; discarding one asks what was off and feeds the SOP's improvement notes. Three frontmatter fields define what a background run may do: `deliverable:` (what you receive; name it or the run has no contract), `research_domains:` (web domains it may fetch), and `research_reads:` (files outside the library it may read). They are honored only on stamped SOPs, so an imported draft nobody reviewed gets no access. Verify the cage on your machine with `scripts/canary_prepare.py` (a few cents of real model runs); re-run it after Claude CLI upgrades, and the runner warns when the version drifts. One accepted residual: a prepared run could leak what it reads via requests to domains the owner declared; declaring a domain is declaring that trust. The budget check is per-run, so a burst of simultaneous clicks can overshoot the monthly cap by a few runs.

Versions are enforced, not honor-system. Every saved SOP carries a fingerprint of its procedure content; if a file is edited outside the normal save flow (a text editor, another tool), the dashboard flags it as "unrecorded changes", unattended runs refuse it for free, and the next session offers to reconcile. Approved edits go through one command (`scripts/sop_version.py bump`) that bumps the version, writes the changelog line, refreshes the fingerprint, and sends a trusted SOP back to active to re-earn its three clean runs. Notes and changelog entries never count as drift; only the steps do. If the library is a git repo (offered at setup), full diff history sits underneath.

## Status

v0.8.0. Built and dogfooded by [Zak Kann](mailto:zak@zakkann.com). What's next lives in [ROADMAP.md](ROADMAP.md).
