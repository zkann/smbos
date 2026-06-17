# Architecture observations from the research

What the 69-tool sweep surfaced specifically about *architecture* (not features). Captured to inform an architecture change before we build the R1-R9 feature set in `recommendations.md`. Nothing here is a decision; it's the discovered signal.

> **Status (eng review, 2026-06-17):** the resolved direction is in `ideal-architecture.md` (the run-object model, built on the current stack) and `stack-architecture.md` (the Electron/Node/Rust re-platform, **deferred**). Two field patterns below were corrected against SmbOS's own code: per-task **worktree/container isolation is code-centric** (business SOPs don't isolate that way), and an **OS-level capability sandbox can't reach business actions** that fire in the external Claude session or via cloud MCP, so SmbOS's cage stays a Claude-CLI permission construct. Read those two docs for the decisions; this stays the raw signal.

## What the field has commoditized (and SmbOS already matches)

The base layer is now the same bet almost everywhere, and it's increasingly free:

- **Local daemon + SQLite + REST/WebSocket + a desktop/browser command center.** HumanLayer's CodeLayer and the open-source `claude-code-command-center` independently shipped the *identical* stack to SmbOS (FastAPI + SQLite + SSE/WebSocket + vanilla/React JS). This validates the plumbing and frees SmbOS to differentiate above it; it also means the plumbing is **not** the moat.
- **Two-tier liveness** (task state vs process-alive state). SmbOS shipped this in 0.30.0 (live / stalled, flock-authoritative). The field calls it a defining primitive; we're current.
- **Plain-markdown, agent-readable, git-stored procedure/spec files** injected as context (AGENTS.md, CRUSH.md, GSD, Backlog.md, Ralph's "prime from external markdown beats long sessions"). SmbOS's SessionStart-hook + `~/sops` is the same architecture, independently rediscovered across the field.

Takeaway: an architecture change should **not** be about re-plumbing the base layer. It should be about the layers below where SmbOS is currently thinner than the field.

## Where the field's architecture is ahead of SmbOS

These are structural, not cosmetic. Each is a candidate axis for an architecture change.

### 1. Per-task isolation (worktree / container per run)
Nearly every serious orchestrator isolates each agent task in its own **git worktree + branch** (Conductor, Claude Squad, Vibe Kanban, aidevops one-worktree-per-worker) or a **container** (container-use, Dagger). The task becomes a self-contained, reviewable unit that can't collide with other work or with the user's live tree.

SmbOS today launches a primed Claude session that runs **in `$HOME` against the live working tree**. There is no per-run isolation: a run mutates files in place, and two runs (or a run plus the user's own work) share one checkout. The repo's own memory already learned this pain at the *dev* level ("concurrent sessions: use a worktree"). The product hasn't applied the same lesson to *runs*.

Implication: a worktree/branch-per-run model would change how `_launch_session` / `run_sop` spawn work, where artifacts land, and how the dashboard references a run's output.

### 2. Runs produce a reviewable artifact, not an in-place mutation
The trust contract across Devin, Genie, Terragon, Aider, Vibe Kanban is "**review the artifact, not the work**": a run lands a diff / PR / draft you accept or discard, never a silent mutation of the working tree. Aider's one-commit-per-edit and container-use's "what they did, not what they claim" are the same idea at finer grain.

SmbOS has a partial version of this only in **prepare mode** (the parked artifact in `pending/`). A normal run has no artifact boundary. This is the architectural root under feature R7 (SOP audit) and R9 (run trace): both are easy if a run produces an inspectable artifact, hard if it doesn't.

### 3. Durable pause/resume with checkpoints (zero idle cost)
The defining HITL primitive is a run that can **pause cheaply, sit in an inbox, and resume exactly where it left off**: LangGraph `interrupt()`, Inngest `step.waitForEvent()`, Trigger.dev waitpoint tokens, HumanLayer `AwaitingHumanApproval`. Idle waiting costs nothing; resume is from a checkpoint, not a restart.

SmbOS's "in flight -> on your plate -> pick up" is the *shape* of this, but a put-back today is a **restart** (a fresh primed session), not a resume from a checkpoint. The `inflight-session-liveness` branch moves toward durable awareness but not yet durable *resume*. Making resume real is an architecture change (what state is a checkpoint, where it lives, how a new session rehydrates it).

### 4. An append-only run ledger (inspectable record vs asserted status)
The strongest trust pattern is an **immutable, inspectable event log of what the agent actually did**: OpenHands EventLog, container-use's command/log history, Amp's shareable threads, Inngest's per-step trace. SmbOS records a status + cost row in `runs.jsonl` and captures a `session_id`, but the run's actual step/tool-call record is not part of the model. "Completed" is asserted, not verifiable.

Implication: promoting the run record from a status row to an append-only, expandable ledger is the substrate that R1 (summary), R9 (trace), and R7 (audit) all sit on.

### 5. A supervisor loop instead of human polling
aidevops's **Pulse** is a lightweight LLM-driven manager that runs every ~2 min (launchd) and triages: merge ready work, dispatch to stuck runs, advance multi-step missions, flag thrashing workers (a "struggle ratio" = messages/commits heuristic), pause at 80% budget. The human supervises a fleet instead of driving each task.

SmbOS has cron + a watchdog but no "manager pass" that decides what to surface on the plate. This is architecturally distinct from a feature: it's a recurring decision loop over the work-state store. Relevant if SmbOS ever runs more than one thing at a time autonomously.

### 6. Multi-agent coordination substrate (only if SmbOS goes parallel)
aidevops coordinates N parallel workers through a **SQLite WAL "mailbox"** (agent registry with role/branch/worktree/heartbeat, inbox/outbox, broadcasts) and persists mission state as **JSON committed to the repo** so any session resumes. Devin Desktop / ACP (Agent Client Protocol) standardize running *third-party* agents in one command center with shared "Spaces" context.

SmbOS is single-run-at-a-time today. If the architecture direction is toward concurrent/background runs, this is the coordination layer the field uses. If it stays one-at-a-time, this is out of scope and worth explicitly deciding *not* to build.

## Strategic note from the research

Two architecture postures the field gets *punished* for, that SmbOS should preserve through any change:

- **Anti-lock-in / your-files / your-model.** Terragon died as a thin cloud wrapper Anthropic replaced; Conductor's full-account OAuth and Raycast's no-BYO-key drew backlash. Any new layer (isolation, checkpoints, ledger) should stay local-first and plain-file-owned, not introduce a hosted dependency or a proprietary store.
- **Plumbing is not the moat.** Don't out-build the command centers on transcript viewers or orchestration UI. The moat is the SOP layer, the do-loop, and the per-SOP audit. An architecture change earns its place only if it makes *those* stronger (e.g., isolation + artifact + ledger make the audit and trust loop real).

## The open architecture questions this raises

1. **Per-run isolation:** should a run execute in a worktree/branch (or container) instead of the live `$HOME` tree? What changes in `run_sop` / `_launch_session` / artifact handling?
2. **Run as artifact:** should every run (not just prepare mode) produce a reviewable diff/draft the owner accepts or discards?
3. **Durable resume:** should put-back / scheduled / paused tasks resume from a checkpoint rather than restart a fresh session? What is the checkpoint, and where does it live as a plain file?
4. **Run ledger:** promote `runs.jsonl` + `session_id` into an append-only, inspectable record that R1/R7/R9 build on?
5. **Concurrency:** does SmbOS stay strictly one-run-at-a-time, or move toward supervised parallel/background runs (which pulls in a coordination substrate and a supervisor loop)? This is the highest-leverage fork: it decides whether items 1, 5, and 6 above are in or out of scope.
