# TODOS

Deferred work, captured with enough context to pick up later.

## Auto handoff: dashboard <-> session focus switch

- **What:** After the manual dashboard-to-session and session-to-dashboard handoff is proven, add a `handoff_intent` record and an automatic focus switch (a running session can flip the dashboard to the relevant view, and a dashboard action can hand a primed session back).
- **Why:** The "seamless, eventually automatic" handoff is the longer-term product goal; the first build only does the manual version.
- **Pros:** Removes the last manual step between the two surfaces; makes the round trip feel continuous.
- **Cons:** Speculative until the manual handoff is in daily use; the auto-focus needs the browser open and listening, with a defined fallback when it isn't.
- **Context:** Came out of the product design session (2026-06-15). Deliberately deferred from the live-mirror rewrite so the core currency + manual handoff ships first.
- **Depends on / blocked by:** The live-mirror dashboard shipping and the manual handoff being trusted.

## Post-cutover: evaluate unifying remaining state into the canonical store

- **What:** Once the new app is the only daemon, evaluate moving the remaining file-based flows (parked approvals, the queue, the run log) into the canonical store for a single query surface.
- **Why:** During the migration the file-based flows stay authoritative so rollback to the old daemon stays real; that constraint disappears after cutover.
- **Pros:** One store to query; removes the file-vs-store split.
- **Cons:** May be unnecessary, the additive split could be the permanent answer; forcing a "finish the migration" can push toward over-unifying. Liveness must stay kernel-lock-authoritative regardless of where metadata lives.
- **Context:** The rewrite uses an additive model (new store holds the new layer; existing file-based flows stay canonical and are read by both the old and new app during overlap). This TODO is the optional end-state, not a commitment.
- **Depends on / blocked by:** Cutover complete (old daemon retired).

## Source-agnostic feedback store for task-to-workflow learning

- **What:** When dashboard feedback on a task (a "wrong lane", "wrong priority", or "unclear title" signal) should teach the workflow that produced it, record it in a source-agnostic store keyed by `(source, item_id)` — parallel to the `routed_item` routing store — rather than in any one source's source-specific verdict log.
- **Why:** The first feedback consumer records verdicts in a source-specific log keyed to that source's id shape. The moment a second ingestion source/consumer exists, its task feedback has nowhere consistent to go, and broker self-audit can't join feedback across sources.
- **Pros:** One feedback surface across every source; cross-source self-audit; symmetric with `routed_item` (record-once + dedup by `(source, item_id)`); the dashboard writes one shape regardless of source.
- **Cons:** Premature with a single consumer (rule of three); a generality with one user today is over-engineering until the second source ships.
- **Context:** Surfaced by the 2026-06-19 eng review of the task-dossier plan. The dossier's feedback loop records into the existing source-specific verdict log, which is correct for the single current consumer. This TODO is the generalization, built when a second ingestion source/consumer lands (alongside the Slack/Linear adapters the broker contract was designed for).
- **Depends on / blocked by:** A second ingestion source/consumer (Slack/Linear adapter), and the dossier feedback loop shipping for the first source.
