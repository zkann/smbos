"""FastAPI dashboard app: the live-mirror server (Lane B of the rewrite).

Runs on its OWN port, ALONGSIDE the legacy stdlib daemon (strangler-fig). It reads the
work-state store and streams changes to the browser over SSE, so the dashboard reflects
reality within ~1s instead of a 90s reload. Read-only for now: `/api/plate` for a snapshot
and `/events` for the live stream. Action endpoints (run/resolve/launch) are ported in a
later step, gated on the legacy daemon's HTTP-layer tests.

Not stdlib: depends on fastapi + uvicorn (see requirements.txt). The legacy daemon stays
stdlib; this app runs under its own venv. Liveness still belongs to the flock, this only
reads metadata via state_store.

DEFERRED (cutover lane): no launchd plist points here yet, so in production this app is
manual-run only (`python scripts/dashboard_app.py` inside a venv with requirements.txt
installed). The venv-aware plist + the legacy->new port swap land when the action endpoints
are ported and the parity tests pass.

Python 3.9+ (asyncio.to_thread / is_disconnected are 3.9-safe).
"""
import argparse
import asyncio
import json
import math
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow `python3 scripts/dashboard_app.py`
import smbos_lib as lib
import state_store as ss
import serve_dashboard as legacy  # reuse the daemon's osascript launch (escaping + permission posture)

def _positive_env(name, default):
    """A positive, FINITE float from env, falling back to `default` for missing/non-numeric/
    <=0/inf/nan. A non-positive value would busy-spin the SSE loop; inf would hang it forever
    (asyncio.sleep(inf)) -- both the availability failures this clamp exists to prevent."""
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)
    return value if (value > 0 and math.isfinite(value)) else float(default)


DEFAULT_PORT = int(os.environ.get("SMBOS_APP_PORT", "8766"))  # 8765 is the legacy daemon
LEGACY_PORT = os.environ.get("SMBOS_DASHBOARD_PORT", "8765")  # the legacy daemon's port
POLL_SECONDS = _positive_env("SMBOS_SSE_POLL", "1.0")        # data_version poll cadence
HEARTBEAT_SECONDS = _positive_env("SMBOS_SSE_HEARTBEAT", "10.0")  # keepalive so the client can detect a dead stream

# During the strangler overlap the legacy dashboard page (served on LEGACY_PORT) may consume
# this app's stream, which is cross-origin (different port). Allow EXACTLY the legacy loopback
# origin, nothing wider, so the Host-guard + token stay the real gate.
LEGACY_ORIGINS = [f"http://127.0.0.1:{LEGACY_PORT}", f"http://localhost:{LEGACY_PORT}"]

# The built Svelte SPA (frontend/ -> `npm run build`). Served same-origin so /events needs
# no CORS. Absent until built; the index route then returns a clear "not built" message.
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Served HTML carries the token: never cache it, never leak ?t= via Referer.
_PAGE_HEADERS = {"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
# Friendly page when someone opens the dashboard without a token (vs a raw "bad or missing token").
_NO_TOKEN_PAGE = (
    "<!doctype html><meta charset=utf-8><title>SmbOS</title>"
    "<body style=\"margin:0;background:#09090b;color:#fafafa;"
    "font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif\">"
    "<main style='max-width:560px;margin:0 auto;padding:48px 32px'>"
    "<h1 style='font-size:20px;font-weight:650'>SmbOS dashboard</h1>"
    "<p style='color:#a1a1aa'>This dashboard needs its access token. Open it with the full URL "
    "ending in <code>?t=&lt;token&gt;</code> from your dashboard launcher.</p></main>"
)


def _sse(event, payload):
    return f"event: {event}\ndata: {payload}\n\n"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _snapshot(sop_dir):
    """The live-mirror snapshots as SSE frames: the plate (waiting), what's in flight, and
    recent runs. Runs in a worker thread (short DB reads) so it never blocks the event loop."""
    return [
        _sse("plate", json.dumps(ss.plate(sop_dir))),
        _sse("inflight", json.dumps(ss.in_flight(sop_dir))),
        _sse("runs", json.dumps(ss.recent_runs(sop_dir))),
    ]


def _launch_prompt(task):
    """The prompt that primes the picked-up session. Derived SERVER-SIDE from the owner's
    stored task (its subject), never from the request body, so the launch's safety invariant
    holds: a browser can only name a task by id, it can't inject a prompt. The subject is
    owner-authored data; were a domain ever to import subjects from an untrusted source (e.g. an
    email subject line), that text becomes natural-language instruction to a session launched in
    the configured permission posture (default 'trust' / acceptEdits) -- a trust boundary to keep
    in mind for any future importer, though not a shell-injection path (open_terminal_with_claude
    shlex-quotes the whole prompt)."""
    subject = (task.get("subject") or "").strip() or "the next task on my plate"
    return ("I'm picking up this task from my dashboard plate: " + subject +
            ". Find the procedure that fits and run it; if none fits, help me do it directly.")


def _launch_session(sop_dir, prompt):
    """Open an interactive Claude session primed with `prompt`, reusing the legacy daemon's
    osascript launch (terminal detection, permission posture, shlex-escaping). A thin seam so
    tests can stub the actual window-spawn. Launches in $HOME, but exports SOP_DIR so the new
    session resolves the SAME library the dashboard is mirroring (it may have been started with a
    non-default --sop-dir); without it the session would fall back to ~/sops and load a different
    library than the one whose plate it was launched from. The SessionStart SOP protocol routes
    Claude to the right folder/procedure from there."""
    sop_dir = Path(sop_dir)
    legacy.open_terminal_with_claude(
        str(Path.home()), prompt,
        terminal=legacy.preferred_terminal(sop_dir),
        permission=legacy.launch_permission(sop_dir),
        env={"SOP_DIR": str(sop_dir.resolve())},
    )


async def event_stream(sop_dir, request):
    """SSE generator. Holds ONE connection so PRAGMA data_version is comparable across polls
    (the counter is not comparable across connections). Emits a plate snapshot on connect,
    a fresh plate whenever the DB changes, and a heartbeat so the client can tell a live but
    quiet stream from a dead one. Stops when the client disconnects."""
    # The held connection (for the cross-poll-comparable data_version) stays on the event-loop
    # thread; data_version is a lockless microsecond read, safe to call inline. plate() opens
    # its own connection and is offloaded to a thread so a slow read can't stall the loop.
    with ss.connect(sop_dir) as conn:
        last_dv = ss.data_version(conn)
        for frame in await asyncio.to_thread(_snapshot, sop_dir):  # initial: plate, inflight, runs
            yield frame
        since_beat = 0.0
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(POLL_SECONDS)
            since_beat += POLL_SECONDS
            dv = ss.data_version(conn)
            if dv != last_dv:
                last_dv = dv
                for frame in await asyncio.to_thread(_snapshot, sop_dir):  # plate, inflight, runs on change
                    yield frame
            if since_beat >= HEARTBEAT_SECONDS:
                since_beat = 0.0
                yield _sse("heartbeat", json.dumps({"ts": _now()}))


def create_app(sop_dir, dist_dir=None):
    """Build the FastAPI app for a given SOP dir. Token is read/created once at startup.
    dist_dir overrides where the built SPA is served from (tests pass a fixture)."""
    sop_dir = Path(sop_dir)
    dist_dir = Path(dist_dir) if dist_dir is not None else DIST_DIR
    token = lib.dashboard_token(sop_dir)
    app = FastAPI(title="SmbOS dashboard", docs_url=None, redoc_url=None)

    # Scoped CORS: only the legacy dashboard origin may consume the stream cross-origin during
    # overlap. Not a wildcard. Token gates access regardless; this just lets the browser expose
    # the response to the legacy page. allow_credentials stays False (the token rides in ?t=,
    # not a cookie).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LEGACY_ORIGINS,
        allow_methods=["GET"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def _guard_host(request, call_next):
        # DNS-rebinding / drive-by-localhost defense: only serve requests addressed to
        # loopback. A malicious page that rebinds a hostname to 127.0.0.1 sends its own
        # Host header, which this rejects (the token is the primary gate; this is depth).
        hostname = (request.headers.get("host") or "").split(":")[0]
        if hostname not in ("127.0.0.1", "localhost"):
            return Response("forbidden host", status_code=403)
        return await call_next(request)

    def check(t):
        # constant-time compare; token arrives as the ?t= query param (matches the legacy daemon)
        if not t or not secrets.compare_digest(t, token):
            raise HTTPException(status_code=401, detail="bad or missing token")

    @app.get("/api/plate")
    def api_plate(t: str = ""):
        check(t)
        return {"plate": ss.plate(sop_dir)}

    @app.get("/api/inflight")
    def api_inflight(t: str = ""):
        check(t)
        return {"inflight": ss.in_flight(sop_dir)}

    @app.get("/api/runs")
    def api_runs(t: str = ""):
        check(t)
        return {"runs": ss.recent_runs(sop_dir)}

    @app.post("/api/launch")
    async def launch(request: Request):
        # Token rides in a custom header (X-SMBOS-Token), not ?t=. A custom (non-safelisted)
        # request header makes a cross-origin POST a *preflighted* request: the browser first
        # sends OPTIONS, and CORSMiddleware answers it only for a permitted origin AND a permitted
        # method. POST is not in allow_methods (GET only) and arbitrary origins aren't in
        # allow_origins, so a browser on any other page can't get past the preflight to POST here
        # -- the CSRF defense for this loopback process-spawner. The token stays the primary gate
        # regardless (an attacker can't read it from the token-gated same-origin page). Note: a
        # same-machine server on the permitted legacy origin is still gated by the token + the
        # GET-only method, not by origin alone.
        check(request.headers.get("x-smbos-token", ""))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        try:
            task = ss.get_task(sop_dir, body.get("task_id"))
        except ss.StateStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if task is None:
            raise HTTPException(status_code=404, detail="no such task")
        # Atomically claim the task (waiting -> in_flight) BEFORE launching: this is the gate
        # that makes a double-click or a second client safe. If we can't claim it, someone
        # already picked it up. We read the subject above (for the prompt) before claiming.
        if not ss.claim_task(sop_dir, task["id"]):
            raise HTTPException(status_code=409, detail="task is not on your plate (already picked up?)")
        # Spawn in a worker thread: the osascript launch shells out (up to ~20s) and must not
        # block the event loop. If it fails, RELEASE the claim (back to waiting) so the task
        # isn't stranded in_flight with no session behind it.
        try:
            await asyncio.to_thread(_launch_session, sop_dir, _launch_prompt(task))
        except ValueError as exc:  # non-macOS / missing folder: a clean, client-visible reason
            ss.set_task_status(sop_dir, task["id"], "waiting")
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            ss.set_task_status(sop_dir, task["id"], "waiting")
            raise HTTPException(status_code=500, detail="could not open a session")
        return {"status": "launched", "task_id": task["id"]}

    @app.get("/events")
    async def events(request: Request, t: str = ""):
        check(t)
        return StreamingResponse(
            event_stream(sop_dir, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    def index(t: str = ""):
        # token-gated like the legacy daemon's page (open /?t=<token>); a missing/bad token gets
        # a friendly HTML page, not a raw "bad or missing token" error
        if not t or not secrets.compare_digest(t, token):
            return Response(_NO_TOKEN_PAGE, status_code=401, media_type="text/html",
                            headers=_PAGE_HEADERS)
        index_html = dist_dir / "index.html"
        if not index_html.is_file():
            return Response("Dashboard UI not built. Run `npm run build` in frontend/.",
                            status_code=503, media_type="text/plain")
        html = index_html.read_text(encoding="utf-8")
        if "</head>" not in html:  # fail loud, not a silently tokenless (blank) dashboard
            return Response("Dashboard UI is missing a </head> anchor for the token; rebuild it.",
                            status_code=500, media_type="text/plain")
        # token charset is url-safe ([A-Za-z0-9_-]); json.dumps wraps it as a JS string literal
        inject = f"<script>window.__SMBOS_TOKEN__={json.dumps(token)}</script>"
        html = html.replace("</head>", inject + "</head>", 1)
        return Response(html, media_type="text/html", headers=_PAGE_HEADERS)

    # The SPA's hashed JS/CSS bundle (no secrets; the token lives only in the injected HTML).
    # Served per-request rather than via a StaticFiles mount: a mount raises a request-time
    # RuntimeError when the dir is missing (the unbuilt default on a fresh clone), whereas this
    # gives a clean 404 pre-build / for a stale hash, serves a late build with no restart
    # (matching the index route), and closes traversal by path containment.
    @app.get("/assets/{path:path}")
    def assets(path: str):
        base = (dist_dir / "assets").resolve()
        target = (base / path).resolve()
        if base not in target.parents or not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description="SmbOS live-mirror dashboard server (FastAPI).")
    ap.add_argument("--sop-dir", default=None)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    sop_dir = lib.resolve_sop_dir(args.sop_dir)
    import uvicorn  # imported here so the module is importable without uvicorn (tests use TestClient)

    uvicorn.run(create_app(sop_dir), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
