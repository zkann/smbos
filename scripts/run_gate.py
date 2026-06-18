"""The run gate + spawn, shared (stdlib-only) by the FastAPI dashboard and the engine-action CLI the
Node broker invokes, so both gate and launch a run through ONE implementation -- the broker owns the
HTTP surface but never re-implements the trust-critical gate/spawn in Node.

Pure: each function takes a sop_dir plus arguments and touches only the library's own files. run_sop
re-enforces the whole cage on the unattended side; gate_run is the early, clean 4xx + the autonomy
coercion the SPA reflects."""

import re
import subprocess
from pathlib import Path

import smbos_lib as lib


def gate_run(sop_dir, sop_id, inputs, prepare=False):
    """Native run gate (shared smbos_lib guards). Returns (sanitized sid, effective_prepare) or
    raises ValueError with an owner-facing message. run_sop re-enforces every one of these on the
    unattended side (the cage lives there); this is the early, clean 4xx + the design D2 rule that
    an interactive_only SOP is refused here so the SPA offers Pick up instead of a headless run.

    `prepare` is the tighter prepare cage (run_sop --prepare): the supervised first run a draft is
    allowed to do. The autonomy dial can also FORCE prepare: a 'prepare_ask' SOP runs in prepare
    mode even when a full run was requested, so the returned effective_prepare may be True even if
    the caller passed prepare=False."""
    sid = re.sub(r"[^a-z0-9-]", "", str(sop_id).lower())
    sop = lib.find_sop(sop_dir, sid) if sid else None
    if sop is None:
        raise ValueError("unknown task")
    if lib.is_interactive_only(sop_dir, sid):
        raise ValueError("This one needs you in the session. Pick it up instead of running it headless.")
    # Autonomy dial: 'with me' refuses any headless run (offer Pick up); 'prepare and ask' forces
    # prepare mode for what would be a full run; 'on its own' runs fully. The cage in run_sop
    # re-enforces this, so this is the early, clean refusal + the prepare coercion the SPA reflects.
    autonomy = lib.autonomy_level(sop_dir, sid)
    if autonomy == "with_me":
        raise ValueError("This one is set to 'With me'. It runs only when you do it together. "
                         "Pick it up instead of running it on its own.")
    status = (lib.frontmatter_field(sop, "status") or "").strip().lower()
    if not prepare and status not in ("active", "trusted"):  # prepare IS how a draft runs first
        raise ValueError("This procedure is still a draft. It needs a supervised first run before it "
                         "can run on its own.")
    if autonomy == "prepare_ask":  # a full run of an active/trusted 'prepare and ask' SOP -> prepare
        prepare = True
    if lib.run_lock_held(sop_dir, sid):
        raise ValueError("This procedure is already running. Its result will appear when it finishes.")
    if lib.has_unrecorded_changes(sop_dir, sid):
        raise ValueError("This procedure was changed outside the normal save flow. Review it first.")
    needed = lib.required_inputs(sop_dir, sid)
    if needed and not inputs:
        raise ValueError(f"This task needs information before it can run: {needed}.")
    return sid, prepare


def spawn_run(sop_dir, sid, inputs=None, prepare=False):
    """Spawn the canonical runner (run_sop) for an SOP, fire-and-forget. Uses the SAME command
    builder the legacy daemon uses (lib.run_sop_command), so the app, the daemon, and the broker
    invoke the runner identically."""
    cmd = lib.run_sop_command(sop_dir, sid, inputs=inputs, prepare=prepare)
    # close the parent's copy of the log fd after Popen dups it into the child (no parent fd leak)
    with (Path(sop_dir) / "trigger.log").open("a") as log:
        subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    return cmd
