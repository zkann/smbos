# SmbOS: the ideal architecture

An opinionated target, drawn from the 69-tool research (`architecture-observations.md`) and the current code (`run_sop.py`, `dashboard_app.py`, `state_store.py`, `smbos_lib.py`, `pending/`, `runs.jsonl`). One thesis, then the pieces, then what to explicitly *not* build, then the migration path.

> **Status (eng review, 2026-06-17):** this run-object model is the **chosen near-term direction**, built on the **current FastAPI + Python + React stack** (the Electron/Node/Rust re-platform in `stack-architecture.md` is deferred). Two corrections from that review apply below: (1) the **capability cage is a Claude-CLI permission construct, not an OS sandbox** (see the corrected section); (2) per-run **isolation via a worktree is for code-touching SOPs only**, business SOPs isolate via the run dir + the Claude-CLI cage, not an OS boundary.

## The thesis: promote "the run" to a first-class durable object

Today a run is ephemeral. `run_sop` spawns a primed Claude session in `$HOME` against the live working tree; it leaves behind a status+cost row in `runs.jsonl`, a `session_id`, and (only in prepare mode) a parked artifact in `pending/`. The run itself is not a thing you can hold, isolate, inspect, or resume.

The single architecture change that earns its place: **make a run a first-class, durable, isolated, inspectable object with a reviewable artifact and a checkpoint.** Every high-value feature the research pointed at (legibility R1/R9, cost R2, autonomy dial R3, SOP audit R7, durable resume) stops being a separate bolt-on and becomes a property of that object. The dashboard's job becomes exactly what PRODUCT.md says: a live mirror over the run-object lifecycle.

This is the right move *because* the research showed the plumbing (FastAPI + SQLite + SSE) is commoditized and the per-task object (worktree + branch + diff + checkpoint) is where the field actually competes. SmbOS is thin exactly there.

## The Run object

A run is a record plus four attachments, all plain files (no new hosted store, no lock-in):

```
run record (one append-only row, in the state store / runs ledger):
  id            run id (lineage: parent_run_id for chained/fanned SOPs)
  sop           which SOP, which version stamp (drift-aware)
  autonomy      with_me | prepare_ask | on_its_own   (the dial, R3)
  status        queued -> running -> parked | paused -> applied | done | dismissed | skipped
  liveness      live | stalled         (orthogonal to status; the 0.30.0 two-tier split)
  cost_usd      actual; plus a pre-run estimate from this SOP's own history (R2)
  summary       one-line plain-language "what it did" (R1)
  workspace     path to the run's isolated work dir (below)
  artifact      path to the reviewable deliverable (below)
  checkpoint    path to the resume state (below)
  session_id    the Claude Code session, for the expand-to-trace escape hatch (R9)
```

The four attachments:

1. **Workspace (isolation).** A run executes in its *own* place, not the live `$HOME` tree. See the next section: this is the part the generic research gets wrong for SmbOS.
2. **Artifact (review the artifact, not the work).** Every non-trusted run parks a reviewable deliverable: a diff for code, a draft for a document, a "here's what I'll send" for an outbound action. Generalize prepare-mode's `pending/` from a special case to the default path for `prepare_ask`. The owner approves/revises/discards the artifact; nothing leaves the sandbox until they do.
3. **Checkpoint (durable resume).** Enough plain-file state that a put-back / paused / scheduled run *resumes* where it left off instead of restarting a fresh primed session. Today a put-back is a restart; the field's defining primitive (LangGraph interrupt, Inngest waitForEvent, Trigger.dev waitpoint) is resume-from-checkpoint at zero idle cost.
4. **Ledger entry (inspectable record).** The run row is append-only and expandable to the real step/tool-call record via `session_id`. "Completed" becomes verifiable, not asserted, the substrate R1 + R7 + R9 all sit on.

## The isolation primitive that actually fits SmbOS (the key insight)

The research says "worktree or container per agent." That is **code-centric** and only half-right for SmbOS, because SmbOS runs *business* SOPs (draft an invoice, send a follow-up, compile a report, onboard a client), not just code. You can't `git worktree` an email send. Copying the field's worktree-per-agent pattern wholesale would be a category error.

The right primitive is **two separable boundaries**, which is exactly PRODUCT.md's "safety is separate from autonomy":

- **A run workspace (where outputs land).** A per-run directory for file outputs and the parked artifact. For an SOP that *touches code*, the workspace is a git worktree + branch (so the diff is the artifact and it can't collide with the live tree or another run, the lesson the repo already learned at the dev level in the "concurrent sessions: use a worktree" memory). For an SOP that touches *business artifacts*, the workspace is just the run dir; the artifact is the draft/deliverable.
- **A capability cage (what a run may touch at all).** The hard boundary: never spend, never message a client, never delete without a checkpoint, unless the SOP is explicitly blessed for it. The risk that matters for business work isn't a merge conflict, it's an email that actually went out. **Enforcement is the Claude-CLI permission model `run_sop` already builds** (`--permission-mode`, `--setting-sources isolation`, allow/deny path lists, `SECRET_READ_DENY_PATHS`), held at **every** autonomy level, independent of the dial. It is **not an OS sandbox**, and its reach is honest about its limit: an action that fires through a cloud MCP connector or inside the external interactive session is gated by the Claude permission model + the SOP's blessed capabilities, not by an OS boundary the engine controls. (This corrects an earlier "enforced at the workspace boundary / real isolation" framing the 2026-06-17 eng review disproved against the code.)

So: autonomy (the dial) decides *how far a run proceeds before it parks for review*; the capability cage decides *what it is allowed to touch*. They compose cleanly onto the Run object's lifecycle:

| Autonomy | Lifecycle path |
|----------|----------------|
| **With me** | No unattended run. Opens a live primed session; you drive. (today's pick-up) |
| **Prepare and ask** | Runs in the workspace inside the capability cage, parks the artifact, waits for one-tap approval. (generalized prepare mode) |
| **On its own** | Runs in the workspace, auto-applies *within* the sandbox, reports back with a summary. Only for blessed SOPs. |

The capability cage holds in all three rows. That is the whole trust model, made architectural.

## Execution model: serial + a supervisor pass (NOT a multi-agent mailbox)

The research's flashiest architecture (aidevops's Pulse supervisor + SQLite mailbox coordinating N parallel workers, Devin Desktop's ACP fleet) is built for *teams running fleets*. SmbOS is one technical operator. My recommendation, and the main reversible fork:

- **Keep runs serializable.** One unattended run at a time, queued. The flock/run-lock already enforces per-SOP exclusion; lean on it. This sidesteps the entire multi-agent coordination substrate (mailbox, agent registry, broadcasts) the field needs only because it runs fleets.
- **Evolve the existing cron + watchdog into one lightweight "supervisor pass"** (the Pulse idea, shrunk to solo scale): a cheap recurring loop over the work-state store that (a) starts the next queued `on_its_own` run if none is live, (b) flags a stalled/thrashing in-flight session onto the plate (a struggle-ratio-style heuristic over the run's own step/commit count), (c) surfaces a missed scheduled run (R8), (d) hard-stops at the budget cap. No new daemon: it's the watchdog's job description, widened.
- **Explicitly defer** the multi-agent mailbox, ACP/third-party-agent hosting, and container isolation. Decide *not* to build them now; they're fleet features and a lock-in/complexity surface a solo local-first tool shouldn't carry. Revisit only if "many things running unattended at once" becomes a real, felt need.

## What stays exactly as it is (the moat and the constraints)

- **Plain markdown, local-first, your-files/your-model/no-account.** Every new attachment (workspace, artifact, checkpoint, ledger) is a plain file or dir under the SOP library or a sibling run dir. No hosted store, no proprietary format, no new network dependency. The research is blunt that the field gets *punished* for violating this (Terragon died; Conductor/Raycast/Warp drew backlash).
- **The do-loop and the SessionStart-hook context injection.** Validated independently across the field (Ralph, AGENTS.md). Don't touch the bet; extend what it produces.
- **FastAPI + SSE + SQLite + the React live mirror.** Commodity, correct, keep it. The change is in the *object it mirrors*, not the plumbing.
- **The moat is the SOP layer + the do-loop + the per-SOP audit**, now made real by the run object. Don't out-build the command centers on trace viewers; link to the session and stop.

## The layered picture

```
┌───────────────────────────────────────────────────────────────┐
│  Live mirror (unchanged plumbing)                             │
│  FastAPI + SSE + React.  Today (Act) | Procedures (Manage).   │
│  Mirrors the Run object lifecycle; never the source of truth. │
├───────────────────────────────────────────────────────────────┤
│  Supervisor pass (evolved cron + watchdog)                    │
│  serial runner · stalled/thrash flagging · missed-run         │
│  recovery · budget hard-stop.   NOT a multi-agent mailbox.    │
├───────────────────────────────────────────────────────────────┤
│  The Run object  ← the architecture change                    │
│  record + workspace + artifact + checkpoint + ledger entry    │
│  autonomy dial = lifecycle path · capability cage = safety │
├───────────────────────────────────────────────────────────────┤
│  Plain-file substrate (unchanged identity)                    │
│  ~/sops markdown SOPs · runs ledger · per-run dirs/worktrees · │
│  pending/ artifacts · session markers.  Your files. Local.    │
└───────────────────────────────────────────────────────────────┘
```

## Why this is the ideal (not just a bigger build)

It collapses nine separate feature recommendations into **one coherent object with a clean lifecycle**, keeps SmbOS's identity intact, sidesteps the field's lock-in mistakes, and explicitly refuses the fleet-scale complexity that doesn't fit a solo operator. It also makes the *uniquely-SmbOS* feature (post-run "did this run follow its SOP?" audit) trivial: the artifact and the ledger are right there to check against the SOP's plaintext rules.

## Migration path (incremental, no big-bang)

The run object can be introduced *behind* today's `runs.jsonl` / `pending/` / state store, so each step ships on its own:

1. **Ledger + summary.** Add `summary` (and the estimate plumbing) to the run row; render it. (R1/R2; additive `state_store` migration, `SCHEMA_VERSION` bump.) This alone is the first durable run-object field.
2. **Artifact-by-default.** Generalize `pending/` from prepare-only to the `prepare_ask` path; add the **Revise** verb. Runs now produce a reviewable artifact.
3. **Workspace isolation.** Give a run its own dir; for code-touching SOPs, a worktree+branch. `run_sop` / `_launch_session` execute there, not in `$HOME`.
4. **Capability cage.** Make the Claude-CLI permission cage explicit per SOP (its blessed capabilities), separate from the autonomy dial. Not an OS sandbox (see the corrected cage section above).
5. **Autonomy dial.** Wire `autonomy:` frontmatter to the lifecycle path; global permission becomes the ceiling. (R3)
6. **Checkpoint + resume.** Put-back / paused / scheduled runs resume from a plain-file checkpoint instead of restarting.
7. **Supervisor pass.** Widen the watchdog into the serial runner + stall/miss/budget surface. (R8)

Steps 1-2 are also the first two feature slices in `recommendations.md`, so the feature work and the architecture work are the same first moves; the architecture framing just changes what they're *building toward* (a Run object) rather than isolated features.

## The one decision that's genuinely yours

The reversible-but-load-bearing fork is **execution model: serial + supervisor (recommended) vs. supervised parallel (pulls in the mailbox/coordination substrate).** I recommend serial for the solo operator and deferring the fleet machinery, but if "several unattended runs at once" is where you see this going, items 3-7 above get heavier (per-run isolation becomes mandatory, not just nice, and a coordination layer comes back into scope). Everything else in this doc holds either way.
