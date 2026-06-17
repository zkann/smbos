#!/usr/bin/env python3
"""Record the outcome of a picked-up dashboard task, from the launched session.

The dashboard's "pick up" opens a Claude session for a plate task and moves the
task to in_flight; this is how that session reports back so the dashboard stops
showing it in flight without the owner resolving it by hand. The launch prompt
tells the session to run this as its last step:

    resolve_task.py --sop-dir <library> <task_id> done       # finished it
    resolve_task.py --sop-dir <library> <task_id> dismissed  # it should not be done
    resolve_task.py --sop-dir <library> <task_id> waiting    # put it back on the plate

It only moves a task OUT of in_flight, and ONLY if it's still in_flight (the
resolve_in_flight_task gate). So a late or duplicate report can't disturb a task
the owner already resolved manually: that's reported as a no-op, not an error,
since the state is already settled.

The launch pins the library with --sop-dir (the resolved path the task was picked
up from), so the report can't land in the wrong library: task ids are per-library
autoincrement, so without pinning, an unset $SOP_DIR in the session would fall
back to ~/sops and could resolve a DIFFERENT task that happens to share the id.
--sop-dir is optional only for manual use; it falls back to $SOP_DIR then ~/sops.
Stdlib only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_store as ss
from smbos_lib import clear_session, resolve_sop_dir

# The outcomes a session may report. A subset of TASK_STATUSES: a session can only move a task
# out of in_flight, never into it ('in_flight' is the claim gate) and never silently delete it.
REPORTABLE = ("done", "dismissed", "waiting")
_LABELS = {"done": "marked done", "dismissed": "dismissed", "waiting": "put back on the plate"}


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    # Pull out the optional --sop-dir DIR before positional parsing. Pinning the library here is
    # what makes the report land in the SAME library the task was picked up from; see module docs.
    sop_dir_override = None
    if "--sop-dir" in argv:
        i = argv.index("--sop-dir")
        if i + 1 >= len(argv):
            sys.exit("--sop-dir needs a directory")
        sop_dir_override = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) != 2:
        sys.exit("usage: resolve_task.py [--sop-dir DIR] <task_id> <done|dismissed|waiting>")
    task_id, status = argv
    if status not in REPORTABLE:
        sys.exit(f"status must be one of {', '.join(REPORTABLE)} (got {status!r})")
    sop_dir = resolve_sop_dir(explicit=sop_dir_override)
    try:
        task = ss.get_task(sop_dir, task_id)
    except ss.StateStoreError as exc:
        sys.exit(str(exc))
    if task is None:
        sys.exit(f"no task with id {task_id}")
    try:
        changed = ss.resolve_in_flight_task(sop_dir, task["id"], status)
    except ss.StateStoreError as exc:
        sys.exit(str(exc))  # a DB-level failure exits cleanly, not as a traceback
    if changed:
        clear_session(sop_dir, task["id"])  # task left in_flight: drop its liveness marker
        print(f"Task {task['id']} {_LABELS[status]}.")
    else:
        # Not in flight: already resolved (by hand, or a prior report). The state is settled, so
        # this is a benign no-op, not a failure: don't clobber what the owner already decided.
        print(f"Task {task['id']} was not in flight (already resolved); nothing changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
