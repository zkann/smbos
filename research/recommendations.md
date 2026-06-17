# SmbOS: recommendations and the ideal version

Derived from the competitive research in `competitive-landscape.md` (69 tools, 10 clusters, 2026-06-17). This doc turns the landscape into a prioritized change list and a wireframe for the next version of SmbOS.

> **Status (eng review, 2026-06-17):** this is the **chosen near-term plan**, built on the **current FastAPI + Python + React stack**. The Electron/Node/Rust re-platform (`stack-architecture.md`) is deferred behind named triggers; the run-object substrate is in `ideal-architecture.md` (with the capability-cage correction: it's a Claude-CLI permission construct, not an OS sandbox). Build order is the Slices below; Slices 1-2 (legibility + cost) are the first tasks.

## The one-paragraph thesis

The architecture (FastAPI + SSE + SQLite + a primed-session do-loop) is now the commodity layer the whole field has converged on. SmbOS's moat is the plain-markdown SOP library, the do-loop, and a calm plain-words operating model for a technical solo operator who owns their files, model, and machine. The next version should not add plumbing. It should finish the **trust loop** the architecture already implies, on three fronts the market proves are scarce: **legibility** (what did a run actually do), **cost** (show it before the click, the loudest complaint in the category), and **graduated trust** (a per-procedure autonomy dial, not a global switch). And it should ship the one thing only SmbOS structurally can: a post-run "did this run follow its SOP?" audit against the plaintext rules.

## What the market taught us (cross-cutting patterns)

1. **Trust, not autonomy, is the scarce resource.** Autonomy is commoditized; the tools that win buy trust with legibility: immutable inspectable run records, trace-per-run views, model-written one-line summaries.
2. **Durable human-in-the-loop pause/resume is the defining primitive.** Agent parks cheaply, sits in an inbox, resumes where it left off. SmbOS's "in flight -> on your plate -> pick up" already IS this, just not yet formally durable.
3. **Graduated/learned trust is replacing the binary on/off toggle.** Gate only risky inputs; surface what changed vs the last approved run.
4. **Cost legibility is the single loudest complaint.** Lindy "expensive" (42 mentions), Devin "$40 for nothing", Factory token "blackhole", Bardeen "rug-pull". The gold standard shows spend before a run and hard-stops at a cap.
5. **Tight scoping separates a good run from a day-long hallucination spiral.** An SOP layer encodes exactly this by design: the cluster's clearest gap, and SmbOS's clearest structural advantage.
6. **Plain-markdown, local-first, git-stored, agent-readable procedures are a loved property** (Backlog.md, GSD, Obsidian, Runme, Warp Notebooks, AGENTS.md). Ralph independently validates that priming from external markdown beats long sessions: SmbOS's SessionStart hook is the same bet.
7. **Anti-lock-in is a wedge users punish you for violating.** Terragon died as a thin cloud wrapper; Conductor's full-GitHub OAuth, Warp's mandatory login, Raycast's no-BYO-key, Claude Code Routines' "I want a commodity not a platform" all drew backlash. Local-first + your-files + your-model is the counter-position.
8. **Silent/opaque state is the universal failure mode.** n8n shows "success" while writing partial data; Lindy agents "vanish from the dashboard"; Motion silently reshuffles. The answer is a live mirror that always shows real state and distinguishes "reported done" from "went quiet."
9. **Two-tier liveness wins:** separate TASK state (waiting/working/done) from PROCESS liveness (alive / exited-but-resumable / stalled). SmbOS shipped exactly this in 0.30.0.
10. **Never present an empty plate on day one;** templates/starter packs solve cold-start everywhere.
11. **Ceremony-vs-quick-task tension recurs:** task-master and GSD are "great for big projects, overkill for a quick fix." A lightweight quick path must coexist with the full SOP ceremony.

## Where SmbOS already wins (protect these)

- The SOP layer is the scoping discipline every autonomous tool makes users reinvent per task.
- SOPs are exercised on every run, so drift is caught by use, not by a separate audit ritual. Plain markdown an agent reads does not break when a UI button moves (Scribe's core weakness).
- Plain-language owner-facing copy ("waiting for you", "on your plate", "in flight", "coming up") is warmth none of the "inbox / approval / control tower" field has.
- The do-loop (task lands -> human picks up -> primed session -> reports completion) is novel in the SOP-docs space: every doc/KB tool stops at DOCUMENT or ANSWER.
- The human pick-up gate is the exact feature the autonomous chief-of-staff tools (Motion, Cora, Lindy) erode trust by lacking.
- Local-first, file-owned, no-seat positioning is clean counter-positioning against credit-metered and per-seat resentment.

## Prioritized recommendations

Ranked by impact then effort. IDs referenced in the build plan below.

| # | Change | Type | Impact | Effort |
|---|--------|------|--------|--------|
| R1 | **Per-run summary line** on Recent runs and resolved tasks (the session already produces it; we discard it) | feature | high | S |
| R2 | **Pre-run cost estimate + live budget headroom** on every Run/Queue/Prepare/Pick-up control | feature | high | M |
| R3 | **Per-procedure autonomy dial** (With me / Prepare and ask / On its own) replacing the global toggle | feature | high | M |
| R4 | **Route "waiting for you" to push/email** so the loop closes off-dashboard | feature | high | M |
| R5 | **One-click "open this session" / take over locally** on an in-flight (esp. stalled) card | ux | medium | S |
| R6 | **Sharpen positioning:** local-first, file-owned, no-credits, your-model, lead the README with it | positioning | medium | S |
| R7 | **Post-run "did this run follow its SOP?" audit** (advisory, routed through propose/approve) | feature | medium | M |
| R8 | **Skip/conditional logic + missed-run recovery** for scheduled SOPs (no-op runs are legible; missed runs are recoverable) | feature | medium | M |
| R9 | **Expandable per-run trace** behind the summary (open the real session; session_id already captured) | feature | medium | L |

### The structural change underneath the list

Most of these only land well if the dashboard becomes the **two zones PRODUCT.md already specifies** but the current React `App.jsx` dropped: an **Act** zone (Today: what needs you + act) and a **Manage** zone (Procedures: the library, edit/harden, autonomy + schedule per SOP). The legacy vanilla dashboard (`assets/`) had more of this (tabs, procedure cards + detail dialog, a "Do this first" lead action, search, spend bar); the React rewrite simplified to the action loop. Reuniting the React app with the documented vision is the frame that R1-R9 hang on.

## Wireframe: the ideal version

Two tabs. Calm by default. Plain words. The action surface trends toward empty as trust grows.

### Tab 1 - Today (the Act zone)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ● SmbOS            Today | Procedures            $3.40 of $20 this month  │  <- live dot + budget headroom (R2)
├─────────────────────────────────────────────────────────────────────────┤
│  Two things are waiting for you. Nothing overdue.                         │  <- one plain status line
│                                                                           │
│  DO THIS FIRST                                                            │  <- single highest-priority action
│  ┃ Approve the invoice draft for the Acme onboarding      [ Review ▸ ]    │
│                                                                           │
│  ON YOUR PLATE ─────────────────────────────────────────────────────────│
│   • Weekly metrics report                  ~$0.12   [ Pick up ▶ ]         │  <- pre-run cost est (R2)
│   • Follow up on the Acme proposal         ~$0.30   [ Pick up ▶ ]         │
│                                                                           │
│  NEEDS YOUR EYES ───────────────────────────────────────────────────────│
│   • Invoice draft · Acme            pending                               │
│       proposed: send to billing@acme.com    [ Approve ] [ Revise ] [ ✕ ]  │  <- show the artifact/args; Revise verb (gap)
│                                                                           │
│  IN FLIGHT ──────────────────────────────────────────────────────────────│
│   ● Drafting the Q2 metrics report                                        │
│       live · 6 min · 4 steps               [ Open session ] [ Done ] [⋯]  │  <- take-over (R5); two-tier liveness (0.30.0)
│   ◐ Reconciling payments                                                   │
│       stalled · window closed              [ Open session ▸ ] [ Put back ]│  <- stalled = resume-where-it-left-off
│                                                                           │
│  COMING UP ──────────────────────────────────────────────────────────────│
│   • Invoice run · every Monday 9:00 AM     in 3 days      [ Run now ]     │  <- plain schedule, no cron
│   ⚠ Payment reconcile · was due yesterday  missed         [ Run now ]     │  <- missed-run recovery (R8)
│                                                                           │
│  RECENT RUNS ─────────────────────────────────────────────────────────────│
│   ✓ Weekly metrics report   "Compiled 4 KPIs, flagged churn up 2%"  $0.11 │  <- per-run summary line (R1)
│       ✓ followed its SOP                                  [ open ▸ ]      │  <- SOP audit verdict (R7) + trace (R9)
│   ✓ Invoice follow-up       "Sent reminder to 2 overdue accounts"   $0.08 │
│   ⚠ Onboarding · Beta Co    "Skipped the welcome-email step"        $0.22 │  <- audit caught a skipped rule
└─────────────────────────────────────────────────────────────────────────┘
```

### Tab 2 - Procedures (the Manage zone)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ● SmbOS            Today | Procedures                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  [ search procedures…             ]   ☐ drafts only   ☐ needs attention  │
│                                                                           │
│  ┌─ Weekly metrics report ───────── trusted ─┐  ┌─ Invoice follow-up ───┐ │
│  │ Autonomy:  ◉ With me               │       │  │ Autonomy:  ◯ With me   │ │  <- per-SOP autonomy dial (R3)
│  │            ◯ Prepare and ask       │       │  │            ◉ Prepare   │ │
│  │            ◯ On its own            │       │  │            ◯ On its own│ │
│  │ Every Monday 9:00 AM · ~$0.11/run  │       │  │ On demand · ~$0.08/run │ │
│  │ 12 clean runs · last ran 3d ago    │       │  │ 4 clean runs           │ │
│  │ [ Run ] [ Queue ] [ Open ▸ ]       │       │  │ [ Run ] [ Queue ]      │ │
│  └────────────────────────────────────┘       └────────────────────────┘ │
│                                                                           │
│  Open ▸ a procedure  →  detail dialog: the SOP markdown, its autonomy     │
│  dial, schedule (plain words), run history with summaries + costs, drift  │
│  flags, and the propose/approve fold-in. Edit stays markdown + Claude.    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Settings (footer, both tabs)

- **Monthly budget** with a live burn meter and a plain "paused: you hit your budget" hard stop (the cap already exists in `run_sop`; this surfaces it). (R2)
- **Notifications:** route act-required items to push/email, opt-in, quiet at zero. (R4)
- **Global permission ceiling** (the autonomy dial's safety floor) + terminal.
- **The capability boundary** ("never spend, never message a client, never delete without a checkpoint") is stated as held at every autonomy level, separate from the dial. (R3, per PRODUCT.md)

## Suggested build sequence (vertical slices, deepest-value first)

Per PRODUCT.md's "go deep on one before wide on all", each slice is shippable on its own.

- **Slice 1 - Legibility (R1 + R5 + R9-lite).** Persist the session's one-line summary on the run row / resolved task (additive `state_store` migration), render it on Recent runs and resolved in-flight items, add "Open session" on in-flight/stalled cards reusing the existing primed-launch plumbing, and link out to the captured `session_id`. Smallest, highest-trust, foundation for everything else.
- **Slice 2 - Cost legibility (R2).** Per-SOP estimate from that SOP's own `runs.jsonl` history (median/p75 of clean runs), shown as a range on every Run/Queue/Prepare/Pick-up control plus month-to-date budget headroom. The data already exists; only the surfacing is missing.
- **Slice 3 - Two-zone restructure + autonomy dial (R3).** Reintroduce Today/Procedures tabs; build the per-procedure autonomy dial into SOP frontmatter (`autonomy: with_me | prepare_ask | on_its_own`, default `with_me`); the dashboard and `run_sop` read it; global permission stays the ceiling. Manual dial only in phase 1; "earn the recommendation after N clean runs" is a fast follow (clean_runs already tracked).
- **Slice 4 - Close the loop off-dashboard (R4)** and **the SOP-audit (R7)**, then **scheduled-run skip/recovery (R8)** and the **positioning pass (R6)**.

## Decisions (status after the 2026-06-17 eng review)

1. **Scope of the first implementation:** RESOLVED - foundational legibility + cost slices first (Slices 1-2), on the current stack, not a big-bang two-zone restructure. The two-zone restructure is Slice 3.
2. **Autonomy dial storage:** SOP frontmatter (plain-markdown, owned, drift-visible) vs `triggers.json` (central config). Frontmatter fits the file-owned identity; **leaning frontmatter**, confirm at Slice 3.
3. **Push routing (R4):** which channel first (the environment has a PushNotification tool; email is also available). Notification noise is the fastest way to make a calm tool anxious, so this needs a deliberate choice. Open; decide at Slice 4.
