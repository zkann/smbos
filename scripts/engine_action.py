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
import sys
from pathlib import Path

import run_gate
import smbos_lib as lib
import state_store as ss


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
    # Atomic gate on still-in_flight: a stale tab clicking again after a recovery must not re-flip it.
    if not ss.resolve_in_flight_task(args.sop_dir, task["id"], args.status):
        print(json.dumps({"detail": "task is not in flight (already resolved?)"}))
        return 9
    lib.clear_session(args.sop_dir, task["id"])  # the task left in_flight: its liveness marker is moot
    print(json.dumps({"status": args.status, "task_id": task["id"]}))
    return 0


def main(argv=None):
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
    ts.set_defaults(func=_task_status)

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
