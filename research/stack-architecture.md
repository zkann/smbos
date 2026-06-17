# SmbOS: target stack and migration plan

The technical-stack architecture (languages/platform/layers) and a migration that keeps the proven Python do-loop running the entire time. This is the "clean up the architecture now, before it's a production app, so we can build faster" plan. Pairs with `ideal-architecture.md` (the language-agnostic run-object model) and `recommendations.md` (the feature set).

> ## Review outcome (eng review, 2026-06-17): RE-PLATFORM DEFERRED, value-first chosen
>
> This document went through `/plan-eng-review` + an independent outside-voice challenge. Decisions:
>
> - **D1:** Initially chose full re-platform now. **Reversed at D5** after the outside voice read the code.
> - **D5 (final):** **Re-sequence to value-first.** Do the run-object work (legibility, cost, autonomy dial, SOP-audit, durable resume from `ideal-architecture.md` + `recommendations.md`) on the **current FastAPI + Python + React stack** now, where it ships user-visible wins fast. **Defer** the Electron + Node broker + Rust native re-platform below until a committed need names it: **multi-user, distribution to non-technical owners, or true OS sandboxing of the engine's own syscalls.**
> - **Why:** the outside voice verified (against the code) that the re-platform front-loads four phases of plumbing with no user-visible win until Phase 5-6, on a stack whose cutover is days old, and that three locked premises don't survive contact with the code (see corrections below). The repo's own `ideal-architecture.md` already concluded the run-object work is the high-value move and the plumbing is not the moat.
>
> **Code-verified corrections to carry IF/WHEN we re-platform** (these retire the weak parts of D2-D4):
> - **D4 (frozen binary) - DROP for now.** The interactive session's SessionStart hook runs the *plugin's* Python on system `python3` from `$CLAUDE_PLUGIN_ROOT`, not a frozen binary, so freezing covers only headless runs while the unfrozen plugin engine stays mandatory. Two engines would drift. Ship one plugin engine for both surfaces; revisit freezing only for non-technical distribution.
> - **D3 (Rust owns the interactive launch) - NARROW.** The `osascript`->Terminal->login-shell chain is what gives the spawned Claude session its PATH, keychain/OAuth auth, `SOP_DIR`/`SMBOS_TASK_ID` env, and macOS TCC grants. `run_sop.py` already carries scar tissue for the minimal-PATH problem. If we re-platform: Rust owns headless spawn + liveness first; the interactive launch stays `osascript` until env/auth/TCC parity is proven, then ports.
> - **Capability cage - reframe.** It is a Claude-CLI permission construct (`--permission-mode`, `--setting-sources`, allow/deny paths), NOT an OS sandbox. Business actions (send email, spend) fire in the *external* session's process tree or via cloud MCP connectors, which Rust cannot sandbox. The cage stays a Claude-CLI / engine-gate concern; do not market it as OS-level enforcement.
> - **D2 (broker sole writer) - holds** as the right model *when* there's a Node broker, but its file-fallback queue reintroduces a dual-writer/merge problem on broker restart; the current flock + append-only ledger model is safer and is what value-first work should keep using now.
> - **"Fixes launchd timers" is mis-attributed:** the launchd-doesn't-fire problem was already solved with cron + kickstart (PR #59). Rust scheduling is not a justification for the re-platform.
>
> **The near-term plan is now `recommendations.md` (Slices 1-4) + the run-object substrate in `ideal-architecture.md`, built on the current stack.** Everything below is the deferred re-platform reference, retained for when a committed need triggers it.

---

## Target layers

| Layer | Language / tech | Owns |
|-------|-----------------|------|
| **Console** | Electron + the existing React renderer | The desktop window, tray, native notifications, IPC to the broker. Cross-platform. |
| **Broker / integrations** | Node / TypeScript (Electron main process) | The local daemon: run-object lifecycle, the live-mirror state stream, the single API/IPC surface, external integrations (OAuth + service SDKs + MCP TS SDK), scheduling orchestration. |
| **Native OS** | Rust (napi-rs addon or stdio sidecar) | Process spawn, cross-platform process liveness, file-watching, scheduling primitives. (Capability enforcement stays the Claude-CLI permission cage, not an OS sandbox - see the correction banner; Rust can at most sandbox the engine's own syscalls.) |
| **Engine** | Python (unchanged) | The proven do-loop: `run_sop`, `smbos_lib`, the run gates, the importer, the MCP server. Spawned by the broker. **Never breaks during migration.** |
| **AI layer** (post-MVP) | Python | SmbOS's own model passes: SOP-audit (R7), session-to-SOP capture, semantic SOP matching, supervisor reasoning. Distinct from the Claude Code sessions the engine spawns. |
| **Substrate** | Plain files + SQLite | `~/sops` markdown SOPs, the run ledger, per-run workspaces, `pending/` artifacts, the work-state DB. Unchanged identity: your files, local, no lock-in. |

Two kinds of "AI" stay distinct: (a) the **Claude Code session** the engine spawns to actually run an SOP (exists today, is the do-loop), and (b) the **AI layer** = SmbOS's *own* model calls for audit/capture (post-MVP). The user's "advanced AI layer, when needed" is (b).

## Target diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  CONSOLE — Electron + React renderer                                  │
│  window · tray · native notifications · IPC                           │
└───────────────▲───────────────────────────────────────────────────────┘
                │ IPC
┌───────────────┴───────────────────────────────────────────────────────┐
│  BROKER — Node / TypeScript  (the local daemon, single API surface)   │
│  run-object lifecycle · live-mirror stream · integrations (Gmail/     │
│  Calendar/Drive/late/…) · scheduling · single SQLite writer           │
└───────▲───────────────────────────────────────────────▲───────────────┘
        │ spawn + JSON/CLI contract                      │ napi / sidecar
┌───────┴────────────────────────┐         ┌─────────────┴───────────────┐
│  ENGINE — Python (unchanged)   │         │  NATIVE — Rust               │
│  run_sop · smbos_lib · gates · │         │  spawn · liveness · watch ·  │
│  importer · MCP server         │         │  schedule · capability cage  │
│        │ spawns                │         └──────────────────────────────┘
│        ▼                       │
│  Claude Code session (runs the SOP)                                    │
└────────────────────────────────┘
        │ reads/writes
┌───────┴────────────────────────────────────────────────────────────────┐
│  SUBSTRATE — plain files + SQLite (~/sops markdown · run ledger ·       │
│  per-run workspaces · pending/ artifacts · work-state DB)              │
└────────────────────────────────────────────────────────────────────────┘
```

Run flow: broker decides to run SOP X → Rust native spawns the Python engine (`run_sop`) in an isolated workspace under the capability cage → the engine spawns the Claude Code session that does the work → the session reports completion → Rust native tracks liveness → broker updates the run object → Electron mirrors it live. The Claude Code plugin (SessionStart hook + commands + MCP) remains the **engine**; Electron/Node/Rust are the console, orchestration, and OS layers around it.

## The invariant: the Python engine runs the whole time

This is a strangler-fig migration (the same pattern `dashboard_app.py` already used to replace the legacy daemon: new layer alongside old, proxying, until the old one is removable). At no phase is the do-loop down. Each phase ships on its own and is independently revertable.

### Phase 0 - Establish the seams (no behavior change)
- Freeze the **run-object schema** as a language-neutral contract (plain files + a documented SQLite schema), so Node, Rust, and Python all read/write the same truth.
- Formalize the **broker↔engine boundary** as a stable CLI/JSON contract. The engine already exposes most of it (`run_sop_command`, `resolve_task.py`, the gates in `smbos_lib`); document these as "the engine API" so a Node caller can drive a Python engine.
- Decide the **single DB writer** (see risks): the broker becomes the writer; the engine writes through the broker or through the shared WAL schema with a documented lock contract.

### Phase 1 - Electron shell around the existing app (thinnest wrap)
- Electron loads the **existing React frontend** as its renderer; for now it can point at the existing FastAPI server on localhost, so the backend is untouched.
- Electron provides the **tray + native notifications**, replacing `tray_app.py` (rumps/pyobjc).
- **Ships:** a cross-platform desktop window + tray + notifications (delivers R4's off-dashboard loop), with zero backend change. Engine untouched.

### Phase 2 - Stand up the Node broker as a facade in front of FastAPI
- The Electron renderer now talks to the **Node broker**; the broker initially just **proxies** every call to the Python FastAPI app.
- Establishes the broker as the single API/IPC surface before any logic moves.
- **Ships:** identical behavior, new front door.

### Phase 3 - Move reads + the live-mirror into the broker
- Migrate the **SSE live-mirror + read endpoints** (plate, inflight, runs, pending, queue, settings) to the broker, reading the SQLite work-state (better-sqlite3) and the plain-file substrate directly. Pure reads, lowest risk.
- FastAPI keeps the write/action endpoints for now.
- **Ships:** the broker owns the live mirror; FastAPI shrinks to actions.

### Phase 4 - Move actions into the broker; broker spawns the Python engine
- The broker's **run / launch / resolve / queue** actions invoke the Python engine via the Phase-0 contract (spawn `run_sop` / `resolve_task`). Engine code unchanged; only its caller flips from FastAPI to Node.
- `dashboard_app.py` and the legacy `serve_dashboard.py` become removable. The engine (`run_sop`, `smbos_lib`, MCP server) stays Python.
- **Ships:** FastAPI gone. Node broker + Python engine.

### Phase 5 - Introduce the Rust native layer
- Replace **osascript launch** with Rust cross-platform process spawn; move **process liveness** (today's flock/pid `inflight-session-liveness` work) into Rust; add **file-watching** and **reliable scheduling** (fixes the documented "Darwin launchd timers never auto-fire / cron-kickstart" workarounds). Exposed via napi-rs or a stdio sidecar.
- The **capability cage** stays the Claude-CLI permission construct (not an OS sandbox); Rust can additionally sandbox the engine's *own* syscalls, but business actions in the external session / via cloud MCP remain gated by the Claude permission model + the SOP's blessed capabilities (correction banner).
- **Ships:** cross-platform launch + robust liveness + reliable scheduling. macOS coupling gone.

### Phase 6 - (Post-MVP) the Python AI layer
- Add SmbOS's own model passes (SOP-audit, capture, semantic match) as a Python service the broker calls, separate from the engine's Claude Code sessions.

Throughout phases 1-5 the engine, the SOPs, and the SessionStart-hook do-loop are live and unchanged.

## Current file → target layer

| Today | Target | Notes |
|-------|--------|-------|
| `frontend/` (React + Vite) | Console (Electron renderer) | Mostly unchanged; gains normal dev tooling/HMR (no longer served as a token-injected single file). |
| `scripts/dashboard_app.py` (FastAPI, SSE, API, launch) | Broker (Node) | Migrated phases 3-4; then removed. |
| `scripts/serve_dashboard.py` (legacy daemon, osascript) | Broker + Rust native | Launch → Rust; API → broker; then removed. |
| `scripts/state_store.py` (SQLite work-state) | Substrate; broker = single writer | Schema frozen in Phase 0; broker owns writes. |
| `scripts/tray_app.py` (rumps/pyobjc) | Console (Electron tray) | Replaced Phase 1; ends macOS-only tray. |
| `scripts/run_sop.py`, `scripts/smbos_lib.py` | **Engine (Python, unchanged)** | The proven loop. Spawned by the broker. |
| `scripts/importer.py`, `sop_triggers.py`, `digest.py` | Engine now; model-driven parts → AI layer later | Mechanical parts could move to the broker over time. |
| `scripts/mcp_server.py` (MCP stdio) | Engine (Python) for now | Stays Python; it's the claude.ai/Desktop surface. Revisit TS reimpl later. |
| `hooks/session-start.sh` (bash) + `commands/*` | Engine (Claude Code plugin) | Unchanged. The plugin is the engine. |
| cron / launchd scheduling | Rust native | Cross-platform, reliable; ends the launchd workarounds. |

## Why this makes the build faster (the goal)

- **One API/IPC surface** (the broker) instead of FastAPI + osascript + a separate tray app + cron-kickstart glue.
- **Integrations get a real home** with first-class Node SDKs and OAuth, instead of only existing inside Claude sessions via MCP.
- **The macOS special-casing ends** (osascript, rumps, launchd-doesn't-fire). One cross-platform native layer.
- **The frontend is freed** from "must be served as one token-injected file by FastAPI" - normal Electron renderer dev loop with HMR.
- **The stdlib-3.9 floor is dropped** for everything except the engine, and the engine can modernize once the broker spawns it rather than the system-python plugin host.
- **Clean layer boundaries enable parallel workstreams** (console, broker, native, engine evolve independently behind stable contracts).

## Risks and open decisions (for the eng review)

1. **Single-writer for the work-state DB.** Today Python (`state_store.py`) writes it; in the target Node reads/writes it too. Pick one writer (recommend the broker) and a documented WAL/lock contract so the engine and broker never race. This is the sharpest concurrency design point.
2. **Broker(Node)↔engine(Python) IPC contract.** Stability, error propagation, and the cost of spawning Python per run (acceptable - runs are coarse-grained, seconds-to-minutes, not hot-path).
3. **Electron footprint** for an always-on background tool (RAM/CPU next to the user's real work). Mitigation: keep a light tray/daemon process; don't hold a heavy renderer resident. (This is the main reason I'd originally have reached for Tauri; Electron is the right call given the Node broker, but footprint needs watching.)
4. **Three build ecosystems** (npm + Rust/cargo + Python) and a heavier CI/release pipeline. Real cost; weigh against the velocity gains above.
5. **Security model shift.** The current FastAPI app's token + Host-guard + CORS + CSRF-via-preflight design exists because it's a localhost HTTP server a browser can reach. Electron in-process IPC **simplifies** this threat model (no drive-by-localhost surface), but any remaining HTTP surface (the future remote-MCP bridge for phone approvals) must keep the token model.
6. **Desktop distribution.** Code-signing + notarization (macOS Gatekeeper, Windows SmartScreen), auto-update. New surface a plugin never had.
7. **The plugin/app relationship.** Confirm the intent: the Claude Code plugin **persists as the engine**, the desktop app is the console around it (not a replacement). The SessionStart hook + spawned Claude Code sessions are still how an SOP runs.
8. **Strategic sequencing.** This is the architecture for the **cross-platform desktop product / broader-market** direction. For the current solo-technical-operator user, the plugin already works; this build is an investment in the productization path (PRODUCT.md: "build for the real user first; the owner version falls out"). Worth an explicit call on whether this is MVP-now or staged.

## What does NOT change

The moat and the identity: plain-markdown SOPs you own, the do-loop, the per-SOP audit, local-first, your-model, no seats, no credits. Every new layer sits *around* that substrate, never replaces it.

## NOT in scope (deferred, with rationale)

- **The Electron + Node + Rust re-platform itself** - deferred per D5 until a committed need (multi-user, non-technical distribution, true OS sandboxing). The body above is its reference design.
- **Frozen engine binary (D4)** - dropped for now; buys little while the plugin engine is mandatory for the interactive session.
- **Rust interactive-launch (D3)** - deferred; `osascript` launch stays until env/auth/TCC parity is proven.
- **OS-level capability cage** - out; the cage is a Claude-CLI/engine-gate construct, not an OS sandbox (can't reach business actions in the external session).
- **Node broker / better-sqlite3 single-writer** - deferred with the re-platform; current flock + append-only ledger stays the writer model.
- **Post-cutover state unification** (the existing TODO) - unchanged; still post-cutover.

## What already exists (reuse, do not rebuild)

- **Live mirror:** `dashboard_app.py` (FastAPI + SSE), the work-state store (`state_store.py`, SQLite WAL, direct-write), the React renderer. The run-object value work extends these, not replaces them.
- **The do-loop:** `run_sop.py` (gates, the cage, `--prepare`), the SessionStart hook, `resolve_task.py` (the engine's existing CLI write-back seam - extend it for the per-run summary).
- **Cost data:** `runs.jsonl` already records `cost_usd`; `sop_triggers.py` already aggregates month-to-date - reuse for the pre-run estimate (R2).
- **Liveness:** the flock + pid/start-time scheme (0.30.0) - keep as the authority; the run-object's live/stalled is already shipped.
- **Artifacts:** `pending/` parked results - generalize to the run-object artifact rather than building a new store.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | codex auth failed (401); outside voice ran via Claude subagent: 10 findings (4 P1), 3 code-verified P1s folded |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 3 architecture decisions (D2/D3/D4) + re-sequence (D5); 0 unresolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

Scope: started full re-platform (D1), **re-sequenced to value-first (D5)** after the outside voice's code-verified findings. Locked architecture calls (carried to the deferred re-platform): D2 broker-sole-writer, D3 Rust headless-first / interactive-launch stays osascript, D4 frozen-binary dropped, capability cage reframed as Claude-CLI not OS-level. Near-term work is the run-object value on the current stack (`recommendations.md` + `ideal-architecture.md`).

- **CODEX:** auth failed (401 token refresh); independent challenge ran via a fresh Claude subagent (genuine separate context, read the repo code).
- **CROSS-MODEL:** the outside voice independently re-derived "do the run-object value on the current stack first" from `ideal-architecture.md`, and verified three premises against the code (frozen-binary buys little while the plugin is mandatory; Rust interactive-launch risks Claude auth/PATH/TCC; OS cage can't reach business actions). The user accepted the re-sequence and the three corrections.
- **VERDICT:** ENG CLEARED — plan re-sequenced to value-first on the current stack; the re-platform is documented and deferred behind named triggers.

NO UNRESOLVED DECISIONS
