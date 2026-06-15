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
from fastapi.responses import Response, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow `python3 scripts/dashboard_app.py`
import smbos_lib as lib
import state_store as ss

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


def _sse(event, payload):
    return f"event: {event}\ndata: {payload}\n\n"


def _now():
    return datetime.now(timezone.utc).isoformat()


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
        yield _sse("plate", json.dumps(await asyncio.to_thread(ss.plate, sop_dir)))
        since_beat = 0.0
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(POLL_SECONDS)
            since_beat += POLL_SECONDS
            dv = ss.data_version(conn)
            if dv != last_dv:
                last_dv = dv
                yield _sse("plate", json.dumps(await asyncio.to_thread(ss.plate, sop_dir)))
            if since_beat >= HEARTBEAT_SECONDS:
                since_beat = 0.0
                yield _sse("heartbeat", json.dumps({"ts": _now()}))


def create_app(sop_dir):
    """Build the FastAPI app for a given SOP dir. Token is read/created once at startup."""
    sop_dir = Path(sop_dir)
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

    @app.get("/events")
    async def events(request: Request, t: str = ""):
        check(t)
        return StreamingResponse(
            event_stream(sop_dir, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
