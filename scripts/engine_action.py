#!/usr/bin/env python3
"""Engine-action CLI: the Node broker invokes this to perform a write/action, so the action path
reuses the exact (stdlib) engine logic instead of re-implementing the trust-critical write/spawn in
Node. Prints a JSON result to stdout; the exit code tells the broker the HTTP status:

  0 -> 200 success     (stdout JSON is the body)
  3 -> 409 refused     (run gate refusal -- {"detail": ...})
  4 -> 404 not found
  8 -> 400 bad request
  9 -> 409 conflict    (e.g. a CAS gate: the task isn't in flight anymore)
  1 -> 500 internal    (anything else; argparse's own bad-usage exit 2 -> 500 too)

Stdlib-only, runs under the system Python 3.9 like the rest of the engine.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import run_gate
import sop_writes
import launch_actions
import settings_io
import serve_dashboard as legacy
import smbos_lib as lib
import state_store as ss
import jobs
import system_status


def _settings_get(args):
    print(json.dumps({"settings": settings_io.read_settings(args.sop_dir)}))
    return 0


def _settings_set(args):
    try:
        result = settings_io.write_setting(args.sop_dir, args.key, args.value)
    except settings_io.BadSetting as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except ValueError as exc:  # bad posture / non-numeric or negative budget / bad terminal
        print(json.dumps({"detail": str(exc)}))
        return 8
    except OSError:
        print(json.dumps({"detail": "could not save the setting"}))
        return 1
    print(json.dumps(result))
    return 0


def _launch(args):
    try:
        result = launch_actions.launch_task(args.sop_dir, args.task_id)
    except launch_actions.BadTaskId as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except launch_actions.UnknownTask as exc:
        print(json.dumps({"detail": str(exc)}))
        return 4
    except launch_actions.AlreadyPickedUp as exc:
        print(json.dumps({"detail": str(exc)}))
        return 9
    except launch_actions.LaunchRefused as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps(result))
    return 0


def _launch_sop(args):
    try:
        result = launch_actions.launch_sop(args.sop_dir, args.id)
    except launch_actions.UnknownTask as exc:
        print(json.dumps({"detail": str(exc)}))
        return 4
    except launch_actions.LaunchRefused as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps(result))
    return 0


def _apply_item(args):
    try:
        result = launch_actions.apply_item(args.sop_dir, args.file, args.index)
    except launch_actions.LaunchRefused as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps(result))
    return 0


def _open_session(args):
    try:
        result = launch_actions.open_session(args.sop_dir, args.task_id)
    except launch_actions.BadTaskId as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except launch_actions.UnknownTask as exc:
        print(json.dumps({"detail": str(exc)}))
        return 4
    except (launch_actions.NotInFlight, launch_actions.StillRunning) as exc:
        print(json.dumps({"detail": str(exc)}))
        return 9
    except launch_actions.LaunchRefused as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps(result))
    return 0


def _queue(args):
    raw = sys.stdin.read() if args.inputs_stdin else (args.inputs or "")
    inputs = raw.strip() or None
    try:
        sid, project = lib.queue_run(args.sop_dir, args.id, inputs=inputs,
                                     scope=args.scope or "here", launch_cwd=args.launch_cwd or None)
    except ValueError as exc:  # unknown task
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps({"status": "queued", "sop": sid, "project": Path(project).name if project else ""}))
    return 0


def _autonomy(args):
    try:
        result = sop_writes.set_autonomy(args.sop_dir, args.id, args.level)
    except sop_writes.BadLevel as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except sop_writes.UnknownSop as exc:
        print(json.dumps({"detail": str(exc)}))
        return 4
    except (sop_writes.DraftNotAllowed, sop_writes.SopDrifted) as exc:
        print(json.dumps({"detail": str(exc)}))
        return 9
    # OSError/ValueError on the write -> the top-level handler -> exit 1 -> 500 (matches FastAPI)
    print(json.dumps(result))
    return 0


def _run(args):
    raw = sys.stdin.read() if args.inputs_stdin else (args.inputs or "")
    inputs = raw.strip() or None
    try:
        sid, prepare = run_gate.gate_run(args.sop_dir, args.id, inputs, args.prepare)
    except ValueError as exc:  # refused: interactive_only / with_me / draft / running / drifted / needs inputs
        print(json.dumps({"detail": str(exc)}))
        return 3
    run_gate.spawn_run(args.sop_dir, sid, inputs=inputs, prepare=prepare)
    print(json.dumps({"status": "preparing" if prepare else "started", "sop": sid}))
    return 0


def _resolve(args):
    # Approve / discard a parked result (mirrors /api/resolve -> lib.resolve_pending_file).
    try:
        status = lib.resolve_pending_file(args.sop_dir, args.file or "", args.decision or "")
    except FileNotFoundError:
        print(json.dumps({"detail": "no such pending item"}))
        return 4
    except ValueError as exc:  # decision not approve/discard
        print(json.dumps({"detail": str(exc)}))
        return 8
    print(json.dumps({"status": status}))
    return 0


def _dequeue(args):
    # Cancel a queued run by removing its queue/ file, basename only (no traversal). Mirrors /api/dequeue.
    target = Path(args.sop_dir) / "queue" / Path(args.file or "").name
    if not target.is_file():
        print(json.dumps({"detail": "no such queued run"}))
        return 4
    try:
        target.unlink()
    except OSError:
        print(json.dumps({"detail": "could not cancel the queued run"}))
        return 1
    print(json.dumps({"status": "dequeued"}))
    return 0


def _task_status(args):
    # Recover / resolve an in_flight task: waiting (put back) / done / dismissed. Mirrors /api/task-status.
    if args.status not in ("waiting", "done", "dismissed"):
        print(json.dumps({"detail": "status must be waiting, done, or dismissed"}))
        return 8
    try:
        task = ss.get_task(args.sop_dir, args.task_id)
    except ss.StateStoreError as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    if task is None:
        print(json.dumps({"detail": "no such task"}))
        return 4
    # from='waiting' (the plate's quiet resolve): clear a WAITING task straight to done/dismissed WITHOUT
    # picking it up. The default (the in-flight recovery) is gated to in_flight + clears the liveness
    # marker, so a stale recovery click can't reflip a put-back task. Each gate is atomic vs a race.
    if getattr(args, "from_status", "") == "waiting":
        if args.status not in ("done", "dismissed"):
            print(json.dumps({"detail": "a waiting task can only be marked done or dismissed"}))
            return 8
        if not ss.resolve_waiting_task(args.sop_dir, task["id"], args.status):
            print(json.dumps({"detail": "task is no longer waiting (picked up or resolved?)"}))
            return 9
    else:
        if not ss.resolve_in_flight_task(args.sop_dir, task["id"], args.status):
            print(json.dumps({"detail": "task is not in flight (already resolved?)"}))
            return 9
        lib.clear_session(args.sop_dir, task["id"])  # the task left in_flight: its liveness marker is moot
    if args.status == "dismissed":  # seed the router-eval corpus from a dashboard dismiss; POST-resolve,
        try:                        # best-effort -- a feedback failure must never affect the dismiss
            ss.record_feedback(args.sop_dir, task["id"], "dismissed")
        except Exception as exc:    # observable, not silent: a broken feedback pipeline surfaces in logs
            print(f"record_feedback failed for task_id={task['id']}: {exc!r}", file=sys.stderr)
    print(json.dumps({"status": args.status, "task_id": task["id"]}))
    return 0


def _job_set(args):
    """Edit a local job spec's schedule/description/enabled. Fields ride on stdin (the description is free
    text). On success returns the fresh system_status so the panel updates at once (and shows 'needs sync')."""
    raw = sys.stdin.read()
    try:
        body = json.loads(raw) if raw.strip() else {}
    except ValueError:
        print(json.dumps({"detail": "bad request body"}))
        return 8
    if not isinstance(body, dict):                       # a JSON array/scalar would crash .get/.in below
        print(json.dumps({"detail": "bad request body"}))
        return 8
    fields = {k: body[k] for k in jobs.EDITABLE_FIELDS if k in body}
    try:
        jobs.set_job_fields(args.sop_dir, body.get("name"), fields)
    except jobs.JobSpecError as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except OSError:
        print(json.dumps({"detail": "could not save the job"}))
        return 1
    print(json.dumps({"ok": True, "system": system_status.system_status(args.sop_dir)}))
    return 0


def _job_create(args):
    """Create a new local job from a stdin spec (command/description are free text). Returns the fresh
    system_status on success."""
    raw = sys.stdin.read()
    try:
        body = json.loads(raw) if raw.strip() else {}
    except ValueError:
        print(json.dumps({"detail": "bad request body"}))
        return 8
    if not isinstance(body, dict):                       # a JSON array/scalar would crash .get/.in below
        print(json.dumps({"detail": "bad request body"}))
        return 8
    fields = {k: body[k] for k in jobs.CREATE_FIELDS if k in body}
    try:
        jobs.create_job(args.sop_dir, fields)
    except jobs.JobSpecError as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except OSError:
        print(json.dumps({"detail": "could not create the job"}))
        return 1
    print(json.dumps({"ok": True, "system": system_status.system_status(args.sop_dir)}))
    return 0


def _job_delete(args):
    """Delete a local job by name. Returns the fresh system_status on success."""
    try:
        jobs.delete_job(args.sop_dir, args.name)
    except jobs.JobSpecError as exc:
        print(json.dumps({"detail": str(exc)}))
        return 8
    except OSError:
        print(json.dumps({"detail": "could not delete the job"}))
        return 1
    print(json.dumps({"ok": True, "system": system_status.system_status(args.sop_dir)}))
    return 0


def _job_build(args):
    """Hand a plain-language job intent to a primed interactive Claude session (it designs + creates the
    job). Not a write itself -- it opens a session; the spec appears when that session authors it."""
    raw = sys.stdin.read()
    try:
        body = json.loads(raw) if raw.strip() else {}
    except ValueError:
        print(json.dumps({"detail": "bad request body"}))
        return 8
    if not isinstance(body, dict):                       # a JSON array/scalar would crash .get/.in below
        print(json.dumps({"detail": "bad request body"}))
        return 8
    intent = (body.get("intent") or "").strip()
    if not intent:
        print(json.dumps({"detail": "describe what the job should do"}))
        return 8
    try:
        launch_actions.build_job(args.sop_dir, intent)
    except Exception:                                    # an osascript / terminal launch failure
        print(json.dumps({"detail": "could not open a session"}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


def main(argv=None):
    # serve_dashboard.LAUNCH_CWD defaults to THIS process's cwd at import -- for the broker-spawned
    # engine that's the Electron/app dir, not a meaningful launch folder. A folder-less launch-sop /
    # apply-item would otherwise open Claude there. Use the configured $SMBOS_LAUNCH_CWD (inherited
    # from the broker), else $HOME -> the fallback treats home as 'no particular project'. Only the
    # engine process does this; the FastAPI dashboard never runs main(), so its LAUNCH_CWD stands.
    legacy.LAUNCH_CWD = os.environ.get("SMBOS_LAUNCH_CWD") or str(Path.home())
    ap = argparse.ArgumentParser(prog="engine_action")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="gate + spawn a run of an SOP")
    r.add_argument("sop_dir")
    r.add_argument("id")
    r.add_argument("--inputs", default=None)
    r.add_argument("--inputs-stdin", action="store_true", help="read inputs from stdin (unbounded; the broker uses this)")
    r.add_argument("--prepare", action="store_true")
    r.set_defaults(func=_run)

    rs = sub.add_parser("resolve", help="approve/discard a parked result")
    rs.add_argument("sop_dir")
    rs.add_argument("--file", default="")
    rs.add_argument("--decision", default="")
    rs.set_defaults(func=_resolve)

    dq = sub.add_parser("dequeue", help="cancel a queued run")
    dq.add_argument("sop_dir")
    dq.add_argument("--file", default="")
    dq.set_defaults(func=_dequeue)

    ts = sub.add_parser("task-status", help="recover/resolve an in_flight task")
    ts.add_argument("sop_dir")
    ts.add_argument("--task-id", dest="task_id", default="")
    ts.add_argument("--status", default="")
    ts.add_argument("--from", dest="from_status", default="")  # 'waiting' = the plate's quiet resolve; else in-flight recovery
    ts.set_defaults(func=_task_status)

    q = sub.add_parser("queue", help="enqueue a run for later")
    q.add_argument("sop_dir")
    q.add_argument("id")
    q.add_argument("--inputs", default=None)
    q.add_argument("--inputs-stdin", action="store_true")
    q.add_argument("--scope", default="here")
    q.add_argument("--launch-cwd", dest="launch_cwd", default=None)
    q.set_defaults(func=_queue)

    au = sub.add_parser("autonomy", help="set a procedure's autonomy dial")
    au.add_argument("sop_dir")
    au.add_argument("id")
    au.add_argument("--level", default="")
    au.set_defaults(func=_autonomy)

    lt = sub.add_parser("launch", help="pick up a plate task (open a primed session)")
    lt.add_argument("sop_dir")
    lt.add_argument("--task-id", dest="task_id", default="")
    lt.set_defaults(func=_launch)

    ls = sub.add_parser("launch-sop", help="pick up an interactive procedure")
    ls.add_argument("sop_dir")
    ls.add_argument("id")
    ls.set_defaults(func=_launch_sop)

    ai = sub.add_parser("apply-item", help="apply one candidate from a parked result")
    ai.add_argument("sop_dir")
    ai.add_argument("--file", default="")
    ai.add_argument("--index", default="")
    ai.set_defaults(func=_apply_item)

    osess = sub.add_parser("open-session", help="reopen a stalled in_flight task's session")
    osess.add_argument("sop_dir")
    osess.add_argument("--task-id", dest="task_id", default="")
    osess.set_defaults(func=_open_session)

    sg = sub.add_parser("settings-get", help="read the owner settings")
    sg.add_argument("sop_dir")
    sg.set_defaults(func=_settings_get)

    sset = sub.add_parser("settings-set", help="apply one owner setting")
    sset.add_argument("sop_dir")
    sset.add_argument("--key", default="")
    sset.add_argument("--value", default="")
    sset.set_defaults(func=_settings_set)

    je = sub.add_parser("job-set", help="edit a local job spec (schedule/description/enabled); fields on stdin")
    je.add_argument("sop_dir")
    je.set_defaults(func=_job_set)

    jc = sub.add_parser("job-create", help="create a new local job; spec on stdin")
    jc.add_argument("sop_dir")
    jc.set_defaults(func=_job_create)

    jd = sub.add_parser("job-delete", help="delete a local job by name")
    jd.add_argument("sop_dir")
    jd.add_argument("--name", default="")
    jd.set_defaults(func=_job_delete)

    jb = sub.add_parser("job-build", help="hand a plain-language job intent to a primed Claude session; intent on stdin")
    jb.add_argument("sop_dir")
    jb.set_defaults(func=_job_build)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # never crash unhandled: the broker maps a non-0/3 to 500
        # The raw exception goes to STDERR (diagnostics), NOT stdout: stdout is the HTTP-facing body
        # the broker returns to the browser, so it must not leak internal detail (paths, etc.).
        print("engine_action: %r" % (exc,), file=sys.stderr)
        print(json.dumps({"detail": "the engine could not complete that action"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
