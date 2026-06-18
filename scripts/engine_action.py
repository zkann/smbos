#!/usr/bin/env python3
"""Engine-action CLI: the Node broker invokes this to perform a write/action, so the action path
reuses the exact (stdlib) engine logic instead of re-implementing the trust-critical gate/spawn in
Node. Prints a JSON result to stdout; the exit code tells the broker the HTTP status:

  0  -> success         (stdout JSON is the 200 body)
  3  -> refused / 4xx   (stdout JSON {"detail": ...} -> the broker returns 409)
  2  -> bad usage       (argparse)
  1  -> internal error  (the broker returns 500)

Stdlib-only, runs under the system Python 3.9 like the rest of the engine.
"""

import argparse
import json
import sys

import run_gate


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
