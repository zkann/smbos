# Roadmap

Working list, maintained as items ship. Shipped history lives in the git log.

## Next up

- Dogfood: let real use reorder this list before adding more modules.

## Later

- **Session-to-SOP capture (conversations become proposed SOP edits).** A `Stop`/`SessionEnd` hook over sessions that touched SOP work runs one cheap pass extracting durable directional statements ("from now on", "we don't say X", a decision-with-rationale) and appends each to the relevant SOP's "Notes for next revision" tagged `via session`. Reuses most of the existing flow: notes section, the diff/approve/bump fold-in, and the SessionStart surfacing, with one small known change: the hook's pending-note scan greps only `via dashboard` today (session-start.sh:91), so it must widen to a shared `via ` pattern (or both tags) to surface `via session` notes too, preserving source attribution rather than mislabeling them `via dashboard`. The hard parts are the real work: (1) the **noise bar** (most "let's try X" is transient, not a rule; conservative or it floods notes); (2) **cost + trust surface** (reading a transcript through a model per session end, the same injection-adjacent surface prepare mode hardened, though it's the owner's own words so lower risk); (3) **routing** a statement to the *right* SOP, not just the one being run, via the index the hook already builds. Motivated by a real long-running session that ran one SOP dozens of times and surfaced several durable rules the in-run learning loop missed because (a) the learning step fires at run end but a long repetitive session never reaches it, (b) a direction about one SOP has no home while you're running a sibling SOP, and (c) a good decision-with-rationale doesn't look like a correction so nothing flags it. Build after a few more real sessions accumulate, so the extractor is designed against what actually got missed; run it through /office-hours + /plan-eng-review first (the noise bar and cost/trust question deserve a cold read). The successor to the dashboard-suggestion flow: same destination, different source.
- **Trigger-miss detection.** When a session realizes mid-task that a matching SOP existed but didn't fire, capture the phrase the user actually used and propose it as a trigger. (The protocol's implicit-feedback rule covers some of this conversationally; make it systematic.)
- **React/shadcn dashboard rewrite: pinned to the remote-bridge milestone, deliberately not before.** Decided 2026-06-10: the shadcn look ships as hand-ported CSS on the zero-dep template. The literal React stack costs distribution (built bundles or npm install on user machines), npm supply-chain surface in a high-trust local tool, a second toolchain in a stdlib-Python repo, and Node in cron/snapshot contexts; it earns those costs only when the dashboard becomes a hosted surface. app.js render functions and the /api/* + embedded-JSON contracts are already shaped for a mechanical port.
- **The night shift (Approach B).** Nightly queue drain in prepare mode (opt-in per task first), morning brief, deliverable/cost previews, results-first Today tab. Includes budget projected-spend: count live prepare lockfiles (with per-SOP cost estimates from runs.jsonl history) toward the monthly cap so click-bursts can't overshoot it.
- **Remote MCP bridge.** The same seven MCP tools over authenticated HTTP so claude.ai web and mobile can reach the library; unlocks phone approvals. Local stdio covers Desktop today.
- **Dashboard direct editing.** Deliberately deferred: suggestions-only preserves the single propose/approve path. Revisit if dashboard suggestions see heavy real use.
- **More SmbOS modules beyond SOPs.** The "operating system" ambition. Shipped: a work-in-progress tracker (v0.14.0). Remaining candidates: a lightweight ops journal, a contacts/commitments tracker, both file-based like SOPs.
- **Wire work items to running SOPs more tightly.** Today advancing a stage is a separate step after running the stage's SOP; could auto-advance on a clean sub-SOP run. And a Linear bridge for code work (event trigger fires the stage SOP; tracking stays in Linear).

## Principles for anything added here

Plain markdown, no lock-in. Diffs, not magic. Actions execute only where the full plugin runs. Plain words on every owner-facing surface.
