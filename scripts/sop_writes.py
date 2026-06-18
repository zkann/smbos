"""Owner-initiated SOP writes, shared (stdlib-only) by the FastAPI dashboard and the engine-action
CLI the Node broker invokes, so both gate + write through ONE implementation -- the trust-critical
fingerprint re-stamp / drift check is never re-implemented in Node.

set_autonomy raises a typed exception per refusal so each caller maps it to its own status (HTTP for
FastAPI, an exit code for the engine) while sharing the message + the actual write."""

import os
import re
import tempfile
from pathlib import Path

import smbos_lib as lib


class SetAutonomyError(Exception):
    """Base for an autonomy-write refusal; the message is owner-facing."""


class BadLevel(SetAutonomyError):
    pass        # -> 400


class UnknownSop(SetAutonomyError):
    pass        # -> 404


class DraftNotAllowed(SetAutonomyError):
    pass        # -> 409 (can't grant a draft full autonomy)


class SopDrifted(SetAutonomyError):
    pass        # -> 409 (stamped body changed out-of-band; the stamp must not bless it)


def _write_autonomy(sop_path, level):
    """Write the `autonomy:` frontmatter field and (re-)STAMP the content_hash, so the owner's
    deliberate choice is fingerprint-protected even on a previously-unstamped SOP: a later out-of-band
    edit (the body, or a silent flip of the level itself) then trips the drift gate and the unattended
    runner refuses it. The drift check + the write share ONE read (no TOCTOU): a STAMPED-but-drifted
    SOP raises SopDrifted rather than letting the re-stamp bless the changed body. Atomic replace."""
    text = sop_path.read_text(encoding="utf-8")
    meta, body = lib.split_frontmatter(text)
    if lib.is_drifted(meta, body):  # stamped + body changed out-of-band: refuse, don't re-stamp it
        raise SopDrifted("This procedure was changed outside the normal save flow. Review it first, "
                         "then set its autonomy.")
    new_hash = lib.content_fingerprint(body, {**meta, "autonomy": level})
    # Unique temp name (not a fixed <sop>.md.tmp) so two concurrent writes to the SAME SOP can't
    # collide on the temp file. Same directory, so os.replace is an atomic rename.
    fd, tmp_name = tempfile.mkstemp(prefix=sop_path.name + ".", suffix=".tmp", dir=str(sop_path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(lib.set_frontmatter_fields(text, {"autonomy": level, "content_hash": new_hash}),
                       encoding="utf-8")
        os.replace(tmp, sop_path)
    finally:
        try:
            tmp.unlink()  # gone after a successful os.replace; cleans up an orphan on failure
        except OSError:
            pass


def set_autonomy(sop_dir, sop_id, level):
    """Validate + gate + write a procedure's autonomy dial. Returns {id, autonomy}. Raises BadLevel /
    UnknownSop / DraftNotAllowed / SopDrifted (the caller maps to a status), or OSError on a write
    failure. 'On its own' requires an active/trusted SOP -- you can't grant a draft full autonomy."""
    level = str(level or "").strip().lower()
    if level not in lib.AUTONOMY_LEVELS:
        raise BadLevel("unknown autonomy level")
    sid = re.sub(r"[^a-z0-9-]", "", str(sop_id or "").lower())
    sop = lib.find_sop(sop_dir, sid) if sid else None
    if sop is None:
        raise UnknownSop("unknown procedure")
    status = (lib.frontmatter_field(sop, "status") or "").strip().lower()
    if level == "on_its_own" and status not in ("active", "trusted"):
        raise DraftNotAllowed("A draft can't run on its own yet. Verify it with a supervised run "
                              "first, then it can earn more autonomy.")
    _write_autonomy(sop, level)  # raises SopDrifted, or OSError/ValueError on a write failure
    return {"id": sid, "autonomy": level}
