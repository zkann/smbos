# Roadmap

Working list, maintained as items ship. Shipped history lives in the git log.

## Next up

- Dogfood: let real use reorder this list before adding more modules.

## Later

- **Trigger-miss detection.** When a session realizes mid-task that a matching SOP existed but didn't fire, capture the phrase the user actually used and propose it as a trigger. (The protocol's implicit-feedback rule covers some of this conversationally; make it systematic.)
- **React/shadcn dashboard rewrite: pinned to the remote-bridge milestone, deliberately not before.** Decided 2026-06-10: the shadcn look ships as hand-ported CSS on the zero-dep template. The literal React stack costs distribution (built bundles or npm install on user machines), npm supply-chain surface in a high-trust local tool, a second toolchain in a stdlib-Python repo, and Node in cron/snapshot contexts; it earns those costs only when the dashboard becomes a hosted surface. app.js render functions and the /api/* + embedded-JSON contracts are already shaped for a mechanical port.
- **Remote MCP bridge.** The same seven MCP tools over authenticated HTTP so claude.ai web and mobile can reach the library; unlocks phone approvals. Local stdio covers Desktop today.
- **Dashboard direct editing.** Deliberately deferred: suggestions-only preserves the single propose/approve path. Revisit if dashboard suggestions see heavy real use.
- **More SmbOS modules beyond SOPs.** The "operating system" ambition. Shipped: a work-in-progress tracker (v0.14.0). Remaining candidates: a lightweight ops journal, a contacts/commitments tracker, both file-based like SOPs.
- **Wire work items to running SOPs more tightly.** Today advancing a stage is a separate step after running the stage's SOP; could auto-advance on a clean sub-SOP run. And a Linear bridge for code work (event trigger fires the stage SOP; tracking stays in Linear).

## Principles for anything added here

Plain markdown, no lock-in. Diffs, not magic. Actions execute only where the full plugin runs. Plain words on every owner-facing surface.
