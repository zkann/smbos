# SmbOS desktop shell (Electron)

Phase 1 of the strangler-fig switchover documented in `research/stack-architecture.md`. A thin Electron shell that wraps the **existing** live dashboard.

## What this phase is

- Opens the running FastAPI dashboard in a real cross-platform desktop window (no browser tab).
- Adds a **tray** icon with the waiting count, and **native notifications** when something lands on your plate (recommendations.md R4, off-dashboard loop), replacing the macOS-only rumps tray.
- The **Python engine and the FastAPI server are untouched.** This shell only *loads* the dashboard; it resolves the URL + token exactly as the rest of the app does. Nothing about the do-loop changes, so the working tool never goes dark.

## What this phase is NOT (yet)

- It does not spawn or own the dashboard server (later phase). It loads whatever server is already running (your launchd dashboard).
- No Node broker, no Rust native layer, no packaging/signing yet. Those are Phases 2-5.

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

2. Node broker as a facade proxying FastAPI (the single API/IPC surface).
3. Move reads + the live mirror to the broker.
4. Move actions to the broker; broker spawns the Python engine.
5. Rust native layer (cross-platform spawn / liveness / scheduling).
