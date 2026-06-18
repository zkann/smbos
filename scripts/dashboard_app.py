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
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow `python3 scripts/dashboard_app.py`
import generate_dashboard as gd  # collect_pending/collect_queued/parse_candidates (parked-result reads)
import run_gate  # the run gate + spawn, shared with the engine-action CLI the broker invokes
import sop_writes  # set_autonomy (gate + fingerprint re-stamp), shared with the engine-action CLI
import launch_actions  # _launch_prompt + _launch_session + launch_task/launch_sop/apply_item, shared with the engine CLI
import smbos_lib as lib
import state_store as ss
import serve_dashboard as legacy  # reuse the daemon's osascript launch + apply_item (launch-coupled)

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


def _runs_with_liveness(sop_dir):
    """Recent runs, each annotated with a derived `state`: 'done'/'error' from the recorded
    result, or for a still-open run (no result yet) 'running' ONLY if the flock for its SOP is
    actually held (lib.active_runs is the liveness authority) AND it's the newest open run for
    that SOP; otherwise 'stalled'. So a run hard-killed without recording its finish shows as
    stalled rather than a false 'running'.

    Liveness is flock-authoritative, but it's correlated to a run row by sop_id + newest-open
    (the run table has no per-run liveness handle). That correlation is exact as long as every
    lock-holding run records its row via start_run -- which run_sop, the only thing that takes
    the lock, does. A future per-run-id join (persisting the marker/pid on the run row) would
    drop that assumption; until then a non-run_sop lock holder could in principle misattribute."""
    runs = ss.recent_runs(sop_dir)
    active = {r["sop"]: r["state"] for r in lib.active_runs(sop_dir)}  # sop_id -> running/stalled
    seen_open = set()  # recent_runs is newest-first: the first open row per SOP is the live candidate
    for r in runs:
        result = r.get("result")
        if result == "error":
            r["state"] = "error"
        elif result:
            r["state"] = "done"
        else:
            sop = r.get("sop_id")
            newest_open = sop not in seen_open
            seen_open.add(sop)
            r["state"] = "running" if (newest_open and active.get(sop) == "running") else "stalled"
    return runs


def _liveness_sig(sop_dir):
    """A cheap, comparable signature of flock-derived run liveness. The SSE loop watches this so
    a run going stalled (a flock release, which writes nothing to the DB and so doesn't move
    data_version) still pushes a fresh runs frame."""
    return tuple(sorted((r.get("sop", ""), r.get("state", "")) for r in lib.active_runs(sop_dir)))


# Per-in_flight-task liveness (live within a startup grace, then stalled) now lives in smbos_lib,
# shared with the open-session recovery in launch_actions. Aliased here so _inflight_with_liveness
# and the tests keep the name.
_task_state = lib.task_state


def _inflight_with_liveness(sop_dir, verify=True):
    """in_flight tasks, each annotated with a derived `state` ('live'|'stalled') so the dashboard's
    in-flight dot tells the truth instead of always showing green."""
    rows = ss.in_flight(sop_dir)
    for t in rows:
        t["state"] = _task_state(sop_dir, t, verify=verify)
    return rows


def _session_sig(sop_dir):
    """A comparable signature of in_flight liveness. A session dying writes nothing to the DB, so
    the SSE loop watches this (like _liveness_sig for runs) to push a fresh inflight frame when a
    task flips live -> stalled. verify=False keeps this once-a-second poll cheap (os.kill only, no
    ps fork): it catches the common window-closed flip; the rendered frame does the full check."""
    return tuple((t["id"], t["state"]) for t in _inflight_with_liveness(sop_dir, verify=False))


def _pending(sop_dir):
    """Parked results still awaiting a decision (status: pending), as API-safe rows.

    Drops the artifact body (the launched session reads that from disk) and keeps only what the
    'Needs your eyes' panel needs: the file id, the source SOP, a human title (from the body's
    '# Pending: X' heading), the candidate list (empty for a single approve/discard), and the
    downstream SOP for an apply. Resolved files (approved/discarded) are filtered out so they
    leave the list."""
    out = []
    for it in gd.collect_pending(sop_dir):
        meta = lib.parse_frontmatter(it["content"])
        if (meta.get("status") or "").strip() != "pending":
            continue
        m = re.search(r"^#\s+(?:Pending:\s*)?(.+)$", it["content"], re.M)
        title = m.group(1).strip() if m else (meta.get("sop") or it["path"])
        out.append({"file": it["path"], "sop": meta.get("sop", ""), "title": title,
                    "candidates": it["candidates"], "next": it["next"]})
    return out


def _dir_mtime_sig(d):
    """A comparable (name, mtime) signature over d/*.md, tolerant of a file that vanishes between
    glob and stat. A concurrent delete (a dequeue, a session removing a finished file) must NOT
    raise out of the SSE signal sampler and tear down the /events stream."""
    sig = []
    for p in d.glob("*.md"):
        try:
            sig.append((p.name, p.stat().st_mtime_ns))
        except OSError:  # removed between glob and stat -> just drop it from this sample
            continue
    return tuple(sorted(sig))


def _pending_sig(sop_dir):
    """Change signature for parked results. They live in files (pending/), so data_version is
    blind to a resolve/new-park; the SSE loop watches this to re-emit the pending frame."""
    pdir = Path(sop_dir) / "pending"
    return _dir_mtime_sig(pdir) if pdir.is_dir() else ()


def _queue(sop_dir):
    """Queued runs (status: queued), for the 'Coming up' panel. Mirrors collect_queued.

    Lifecycle note: nothing auto-drains the queue. A queued run is written by queue_run and
    leaves only via /api/dequeue (Cancel) or by the owner picking it up to run; there is no
    automatic slot/runner, so 'Coming up' is a queued to-do list, not an auto-run schedule."""
    out = []
    qdir = Path(sop_dir) / "queue"
    if qdir.is_dir():
        for p in sorted(qdir.glob("*.md")):
            try:
                m = lib.parse_frontmatter(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):  # skip an unreadable queue file, don't drop the list
                continue
            if (m.get("status") or "").strip() != "queued":
                continue
            out.append({"file": p.name, "sop": m.get("sop", p.stem),
                        "project": Path(m["project"]).name if m.get("project") else ""})
    return out


def _queue_sig(sop_dir):
    """Change signature for queued runs (file-based, like pending/), watched by the SSE loop."""
    qdir = Path(sop_dir) / "queue"
    return _dir_mtime_sig(qdir) if qdir.is_dir() else ()


def _cost_estimates(sop_dir):
    """Per-SOP cost estimate and month-to-date spend, read once from runs.jsonl so the owner sees
    the likely cost (and how much budget is left) BEFORE clicking Run / Queue / Prepare. The
    estimate is the MEDIAN cost_usd of that SOP's prior SUCCESSFUL (result 'ok') runs: median, not
    mean, so a single expensive outlier doesn't skew it; only 'ok' runs, so a cheap failed/refused
    run doesn't lowball it. Returns {sop_id: {estimate, n}} (n = runs it's based on) plus the
    month-to-date total. Best-effort: a malformed or non-numeric line is skipped, never raised."""
    log = Path(sop_dir) / "runs.jsonl"
    by_sop, month_total = {}, 0.0
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    if log.exists():
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cost = r.get("cost_usd")
            # exclude bool (an int subclass: a stray True would count as $1) and non-finite/negatives
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) \
                    or not math.isfinite(cost) or cost < 0:
                continue
            if str(r.get("ts", "")).startswith(month_prefix):
                month_total += cost
            if r.get("result") == "ok":
                by_sop.setdefault(str(r.get("sop", "")), []).append(float(cost))
    estimates = {}
    for sop, costs in by_sop.items():
        costs.sort()
        n = len(costs)
        med = costs[n // 2] if n % 2 else (costs[n // 2 - 1] + costs[n // 2]) / 2
        estimates[sop] = {"estimate": round(med, 4), "n": n}
    return {"estimates": estimates, "month_to_date": round(month_total, 2)}


def _procedures(sop_dir):
    """The SOP library for the Procedures view: each SOP with the facts the UI needs to pick its
    action (Pick up for interactive_only, Prepare for a draft, Run/Queue otherwise). The server
    re-gates at run time, so this read doesn't need drift/lock state."""
    ests = _cost_estimates(sop_dir)["estimates"]
    out = []
    for p in lib.iter_sops(sop_dir):
        try:
            m = lib.parse_frontmatter(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):  # one unreadable SOP must not drop the whole list
            continue
        sid = m.get("id") or p.stem
        out.append({
            "id": sid,
            "title": m.get("title") or sid,
            "draft": (m.get("status") or "").strip().lower() not in ("active", "trusted"),
            "interactive": (m.get("interactive_only") or "").strip().lower() in ("true", "yes", "1"),
            "needs_inputs": bool(m.get("run_inputs")),
            "cost": ests.get(sid),  # {estimate, n} from prior 'ok' runs, or None (no history yet)
            "autonomy": lib.autonomy_level_from_meta(m),  # with_me|prepare_ask|on_its_own (derived if unset)
        })
    return sorted(out, key=lambda x: x["title"].lower())


async def _body_obj(request):
    """Parse a POST body as a JSON object or raise 400. Shared by the action endpoints."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    return body


def _settings(sop_dir):
    """Current owner config for the Settings panel, reusing the daemon's config readers
    (they read triggers.json). Digest controls are deferred to the launchd-cutover PR."""
    budget = 0.0
    try:
        tj = json.loads((Path(sop_dir) / "triggers.json").read_text(encoding="utf-8"))
        if isinstance(tj, dict):
            parsed = float(tj.get("monthly_budget_usd") or 0)
            # float('nan'/'inf') parses without raising; clamp so a bad stored value can't break
            # JSON serialization of this response (set_budget rejects them, but be defensive)
            budget = parsed if (math.isfinite(parsed) and parsed >= 0) else 0.0
    except (OSError, ValueError, TypeError):
        pass
    return {
        "launch_permission": legacy.launch_permission(sop_dir),  # trust / ask / skip
        "terminal": legacy.preferred_terminal(sop_dir),          # terminal / iterm
        "budget": budget,
        "spent": _cost_estimates(sop_dir)["month_to_date"],      # month-to-date, for budget headroom
    }


# Per-setting writers (reuse the daemon's validators; each raises ValueError on a bad value).
_SETTERS = {
    "launch_permission": legacy.set_launch_permission,
    "terminal": legacy.set_terminal,
    "budget": legacy.set_budget,
}


# The run gate + spawn now live in run_gate (stdlib), shared with the engine-action CLI the Node
# broker invokes, so the app and the broker gate/launch a run through ONE implementation. Imported
# under the historical names so /api/run and the tests (which monkeypatch _spawn_run) are unchanged.
_gate_run = run_gate.gate_run
_spawn_run = run_gate.spawn_run


def _snapshot(sop_dir):
    """The live-mirror snapshots as SSE frames: the plate (waiting), what's in flight, parked
    results awaiting a decision, and recent runs (with liveness). Runs in a worker thread so it
    never blocks the event loop."""
    return [
        _sse("plate", json.dumps(ss.plate(sop_dir))),
        _sse("inflight", json.dumps(_inflight_with_liveness(sop_dir))),
        _sse("pending", json.dumps(_pending(sop_dir))),
        _sse("queue", json.dumps(_queue(sop_dir))),
        _sse("runs", json.dumps(_runs_with_liveness(sop_dir))),
    ]


async def event_stream(sop_dir, request):
    """SSE generator. Holds ONE connection so PRAGMA data_version is comparable across polls
    (the counter is not comparable across connections). Emits a snapshot on connect, a fresh
    snapshot whenever the DB changes OR run liveness changes, and a heartbeat so the client can
    tell a live but quiet stream from a dead one. Stops when the client disconnects."""
    # The held connection (for the cross-poll-comparable data_version) stays on the event-loop
    # thread; data_version is a lockless microsecond read, safe to call inline. The snapshot and
    # the liveness read open their own files and are offloaded to a thread so a slow read can't
    # stall the loop. Liveness (a flock release on a dying run) writes nothing to the DB, so
    # data_version alone would miss a run going stalled; we watch it separately.
    def _signals():
        # run liveness (flock), picked-up session liveness (pid), and the file-based work (pending/
        # + queue/) all change without a DB write, so data_version alone would miss them; sample
        # them off the event loop.
        return (_liveness_sig(sop_dir), _session_sig(sop_dir),
                _pending_sig(sop_dir), _queue_sig(sop_dir))

    with ss.connect(sop_dir) as conn:
        last_dv = ss.data_version(conn)
        last_sig = await asyncio.to_thread(_signals)
        for frame in await asyncio.to_thread(_snapshot, sop_dir):  # initial: plate, inflight, pending, runs
            yield frame
        since_beat = 0.0
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(POLL_SECONDS)
            since_beat += POLL_SECONDS
            dv = ss.data_version(conn)
            sig = await asyncio.to_thread(_signals)
            if dv != last_dv or sig != last_sig:
                last_dv, last_sig = dv, sig
                for frame in await asyncio.to_thread(_snapshot, sop_dir):  # all frames on any change
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
    # Serialize settings writes: the reused setters do an unlocked read-modify-replace of the whole
    # triggers.json, so two concurrent apply-on-change POSTs (e.g. a terminal select that also blurs
    # the budget field) could each read the old file and the later replace drop the earlier setting.
    # Created lazily on first use: asyncio.Lock() binds to the running loop, and on Python 3.9
    # constructing one with no running loop raises "no current event loop" (the system py CI catches).
    settings_lock = None
    # The folder the dashboard was launched from, captured ONCE at startup (mirrors the legacy
    # daemon's LAUNCH_CWD): a queued folder-less SOP inherits it. Read live, Path.cwd() would be the
    # same value (the server never chdir's), but binding it once is explicit and future-proof.
    launch_cwd = str(Path.cwd())
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
        return {"inflight": _inflight_with_liveness(sop_dir)}

    @app.get("/api/runs")
    def api_runs(t: str = ""):
        check(t)
        return {"runs": _runs_with_liveness(sop_dir)}

    @app.get("/api/pending")
    def api_pending(t: str = ""):
        check(t)
        return {"pending": _pending(sop_dir)}

    @app.get("/api/settings")
    def api_settings(t: str = ""):
        check(t)
        return {"settings": _settings(sop_dir)}

    @app.get("/api/procedures")
    def api_procedures(t: str = ""):
        check(t)
        return {"procedures": _procedures(sop_dir)}

    @app.post("/api/launch-sop")
    async def launch_sop(request: Request):
        # Pick up an interactive procedure: open a session primed to run it. Reuses the legacy
        # launch (kind=sop), which derives the folder + prompt server-side from the SOP file --
        # the browser sends only the id, never a prompt. Launch-coupled, so offloaded to a thread.
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            return await asyncio.to_thread(launch_actions.launch_sop, sop_dir, body.get("id"))
        except launch_actions.UnknownTask as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except launch_actions.LaunchRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="could not open a session")

    @app.post("/api/settings")
    async def settings(request: Request):
        # apply-on-change: one control per POST ({key, value}). Header-token gated. The setters
        # write triggers.json (set_launch_permission shells nothing, but keep the to_thread for
        # symmetry with future digest setters that shell out). The dangerous 'skip' permission is
        # gated by an inline confirm in the SPA, not here -- the owner authoritatively owns config.
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        setter = _SETTERS.get(str(body.get("key") or ""))
        if setter is None:
            raise HTTPException(status_code=400, detail="unknown setting")
        nonlocal settings_lock
        if settings_lock is None:  # first request: a loop is running, so this is py3.9-safe
            settings_lock = asyncio.Lock()
        async with settings_lock:  # one read-modify-replace of triggers.json at a time
            try:
                await asyncio.to_thread(setter, sop_dir, body.get("value"))
            except ValueError as exc:  # bad posture / non-numeric or negative budget / bad terminal
                raise HTTPException(status_code=400, detail=str(exc))
            except OSError:            # triggers.json write failed (perms / disk) -- server-side
                raise HTTPException(status_code=500, detail="could not save the setting")
            return {"settings": _settings(sop_dir)}  # echo the full new state so the SPA syncs

    @app.post("/api/run")
    async def run(request: Request):
        # gate natively (shared guards), then fire-and-forget Popen run_sop -- run_sop owns the
        # full cage (interactive_only/draft/lock/inputs/permission). Header-token gated.
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        inputs = str(body.get("inputs") or "").strip() or None
        prepare = str(body.get("mode") or "").strip().lower() == "prepare"  # the tighter prepare cage
        try:
            sid, prepare = _gate_run(sop_dir, body.get("id", ""), inputs, prepare)
        except ValueError as exc:  # refused: interactive_only / with_me / draft / running / drifted / needs inputs
            raise HTTPException(status_code=409, detail=str(exc))
        # prepare may have been forced True by a 'prepare and ask' autonomy level
        _spawn_run(sop_dir, sid, inputs=inputs, prepare=prepare)
        return {"status": "preparing" if prepare else "started", "sop": sid}

    @app.post("/api/autonomy")
    async def set_autonomy(request: Request):
        """Set a procedure's autonomy dial (with_me | prepare_ask | on_its_own). Header-token gated.
        'On its own' requires an active/trusted SOP -- you can't grant full autonomy to an unverified
        draft. The write ALWAYS (re-)stamps, so the owner's deliberate choice is fingerprint-protected
        even on a previously-unstamped SOP (a later silent flip then trips drift); a stamped-but-drifted
        SOP is refused (review it first) so the stamp can't bless an out-of-band body edit."""
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            return await asyncio.to_thread(sop_writes.set_autonomy, sop_dir, body.get("id"), body.get("level"))
        except sop_writes.BadLevel as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except sop_writes.UnknownSop as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (sop_writes.DraftNotAllowed, sop_writes.SopDrifted) as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except (OSError, ValueError):
            raise HTTPException(status_code=500, detail="could not save the autonomy setting")

    @app.get("/api/queue")
    def api_queue(t: str = ""):
        check(t)
        return {"queue": _queue(sop_dir)}

    @app.post("/api/dequeue")
    async def dequeue(request: Request):
        # cancel a queued run by removing its queue/ file (basename only, so no traversal).
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        target = Path(sop_dir) / "queue" / Path(str(body.get("file") or "")).name
        if not target.is_file():
            raise HTTPException(status_code=404, detail="no such queued run")
        try:
            target.unlink()
        except OSError:
            raise HTTPException(status_code=500, detail="could not cancel the queued run")
        return {"status": "dequeued"}

    @app.post("/api/queue")
    async def queue(request: Request):
        # enqueue a run for later (writes queue/), reusing the relocated queue_run.
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            sid, project = lib.queue_run(
                sop_dir, body.get("id", ""),
                inputs=str(body.get("inputs") or "").strip() or None,
                scope=str(body.get("scope") or "here"), launch_cwd=launch_cwd)
        except ValueError as exc:  # unknown task
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "queued", "sop": sid,
                "project": Path(project).name if project else ""}

    @app.post("/api/resolve")
    async def resolve(request: Request):
        # header token (CSRF: forces a preflight the GET-only CORS blocks); a quick file write,
        # not a spawn, so it runs inline. The SSE pending signature reflects it within ~1s.
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            status = lib.resolve_pending_file(sop_dir, str(body.get("file") or ""),
                                              str(body.get("decision") or ""))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="no such pending item")
        except ValueError as exc:  # decision not approve/discard
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": status}

    @app.post("/api/apply-item")
    async def apply_item(request: Request):
        # acts on one candidate from a parked result by launching the source SOP's next: SOP.
        # legacy.apply_item is launch-coupled (osascript) and not yet relocated, so it's reused
        # via the legacy import (as /api/launch does) and offloaded to a thread (it shells out).
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            return await asyncio.to_thread(launch_actions.apply_item, sop_dir,
                                           body.get("file"), body.get("index"))
        except launch_actions.LaunchRefused as exc:  # bad index / no candidates / no next SOP / non-macOS
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="could not apply the item")

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
        body = await _body_obj(request)
        # launch_task does the claim CAS + clear_session + the osascript launch + release-on-failure;
        # it's shared with the engine CLI so the broker never re-implements it (the launch-coupled
        # osascript runs in a worker thread, up to ~20s).
        try:
            return await asyncio.to_thread(launch_actions.launch_task, sop_dir, body.get("task_id"))
        except launch_actions.BadTaskId as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except launch_actions.UnknownTask as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except launch_actions.AlreadyPickedUp as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except launch_actions.LaunchRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="could not open a session")

    @app.post("/api/task-status")
    async def task_status(request: Request):
        """Recover or resolve a task from the dashboard: move it back to 'waiting' (put it back on
        the plate), 'done', or 'dismissed'. The owner's manual control for an in-flight task; the
        dashboard also surfaces when a picked-up session has gone stalled (its window closed), so
        this is the action that clears such a task instead of leaving it a one-way trap."""
        check(request.headers.get("x-smbos-token", ""))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        target = body.get("status")
        if target not in ("waiting", "done", "dismissed"):
            raise HTTPException(status_code=400, detail="status must be waiting, done, or dismissed")
        try:
            task = ss.get_task(sop_dir, body.get("task_id"))
        except ss.StateStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if task is None:
            raise HTTPException(status_code=404, detail="no such task")
        # gate on still-in_flight (atomic): a stale row/tab clicking again after a recovery must not
        # flip the now-resolved task into a different state. SSE inflight/plate frames reflect it.
        if not ss.resolve_in_flight_task(sop_dir, task["id"], target):
            raise HTTPException(status_code=409, detail="task is not in flight (already resolved?)")
        lib.clear_session(sop_dir, task["id"])  # task left in_flight: its liveness marker is moot
        return {"status": target, "task_id": task["id"]}

    @app.post("/api/open-session")
    async def open_session(request: Request):
        """Re-open a primed Claude session for a task that is already in flight. The recovery for a
        STALLED pickup (its window was closed, or it crashed without reporting): the dashboard
        otherwise strands it at Put back / Done / Dismiss, with no way to resume the actual work.
        This launches a fresh primed session for the SAME task without re-claiming it (the task
        stays in_flight), so the new session's SessionStart hook re-records the liveness marker and
        the work continues. A late report from the prior dead session is still gated by
        resolve_in_flight_task, so it cannot clobber the resumed task. Token rides in the header
        (same CSRF posture as /api/launch). Launch-coupled, so offloaded to a thread."""
        check(request.headers.get("x-smbos-token", ""))
        body = await _body_obj(request)
        try:
            return await asyncio.to_thread(launch_actions.open_session, sop_dir, body.get("task_id"))
        except launch_actions.BadTaskId as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except launch_actions.UnknownTask as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (launch_actions.NotInFlight, launch_actions.StillRunning) as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except launch_actions.LaunchRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="could not open a session")

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
