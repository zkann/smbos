# SmbOS desktop shell (Electron)

Phases 1-2 of the strangler-fig switchover documented in `research/stack-architecture.md`. An Electron shell wrapping the **existing** live dashboard, now with a Node broker in front.

## What this is

- **Window (Phase 1):** opens the dashboard in a cross-platform desktop window (no browser tab); a **tray** with the waiting count; **native notifications** when something lands on your plate (recommendations.md R4), replacing the macOS-only rumps tray.
- **Node broker (Phase 2):** a `broker.js` reverse proxy (`createBroker`) sits between the renderer and FastAPI. The window and the tray poll talk to the broker; the broker forwards every request to the running FastAPI server, streaming responses (so the `/events` SSE live mirror passes through unbuffered) and preserving the token gate. This establishes the single API/IPC front door before any logic moves off FastAPI.
- The **Python engine and the FastAPI server are untouched.** The shell + broker only *front* the dashboard. Nothing about the do-loop changes, so the working tool never goes dark.

## What this is NOT (yet)

- The broker only **forwards**; no read/action logic has moved to it yet (Phases 3-4).
- It does not spawn or own the FastAPI server. It fronts whatever server is already running (your launchd dashboard).
- No Rust native layer, no packaging/signing yet. Those are Phases 4-5.

## Run it (dev)

The dashboard server must be running. Either your normal launchd dashboard, or start it manually on the port the shell expects (the shell defaults to `8765`; `dashboard_app.py` itself defaults to `8766`, so pass `--port` to match):

```
# manual server, on the port the shell looks for
python scripts/dashboard_app.py --port 8765   # in the dashboard venv

cd desktop
npm install
npm start
```

It resolves the server like the rest of the app: `$SMBOS_DASHBOARD_PORT`, else `triggers.json` `dashboard_port`, else `8765`; token from `<sop_dir>/.dashboard-token`; `sop_dir` from `$SOP_DIR`, else `~/sops`. To point the shell at a different port, set `$SMBOS_DASHBOARD_PORT` (it must match the server's `--port`).

## Next phases

3. Move reads + the live mirror off FastAPI into the broker (serve them directly).
4. Move actions into the broker; the broker spawns the Python engine.
5. Rust native layer (cross-platform spawn / liveness / scheduling).
