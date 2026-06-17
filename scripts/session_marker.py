#!/usr/bin/env python3
"""Record a picked-up session's liveness marker, called from the SessionStart hook.

When the dashboard launches a session for a plate task it exports SMBOS_TASK_ID; the hook runs
this with that id and the claude process pid (the hook's $PPID) so the dashboard can tell a live
pickup from one whose window was closed. It runs in EVERY session's hook path, so it must never
disrupt a normal session: anything unexpected (no id, bad pid, no library) is a silent no-op.
Resolves the library from $SOP_DIR (exported into the session at launch). Stdlib only.

Usage: session_marker.py record <task_id> <pid>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smbos_lib import record_session, resolve_sop_dir


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if len(argv) != 3 or argv[0] != "record":
        return 0  # not our shape; stay silent (the hook fires for every session)
    _, task_id, pid = argv
    try:
        sop_dir = resolve_sop_dir(exit_on_missing=False)
        if sop_dir is None:
            return 0
        record_session(sop_dir, int(task_id), int(pid))
    except (ValueError, OSError):
        return 0  # never disrupt session start over a liveness marker
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
