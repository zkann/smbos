"""jobs.py -- the smbos recurring-jobs manager (stdlib-only).

Declarative cron jobs. Each job is a JSON spec in a `jobs.d/` directory: a PUBLIC one shipped with
the plugin, plus a LOCAL `<sop_dir>/jobs.d` for private specs that never enter the public repo.
`jobs sync` compiles the enabled specs into tagged crontab lines, idempotently, reusing the proven
crontab IO + escaping from the dashboard watchdog (cutover_dashboard.install_watchdog).

Scope, deliberately small (cron lines only):
  - kind="job":          a direct cron line running the spec's command.
  - kind="keychain-job": a cron line that `launchctl kickstart`s an existing GUI agent
                         (com.smbos.<name>), the workaround for cron being unable to read the login
                         keychain. The agent's plist is managed elsewhere; this owns only its cron line.
Always-on SERVICES (the dashboard/tray/desktop launchd agents) are NOT modeled here -- they have
rollback/KeepAlive concerns a cron compiler must not touch, and a disabled rollback agent must never
be reaped. There is no run-heartbeat: a job's liveness is observable from its own output file.

Operational: macOS blocks `crontab` WRITES without Full Disk Access, so `jobs sync` must run from an
interactive Terminal / the installer, never the (FDA-less) broker process.

    jobs.d/<name>.json:  {"name","kind","schedule","command"?,"claims"?,"enabled"?}
      name      [a-z0-9-], used verbatim in the cron tag + the launchctl label
      schedule  a literal cron timing field, e.g. "30 8 * * *" or "@daily"
      command   the shell command (job only); must be self-contained (cron's env is minimal)
      claims    optional: a legacy cron tag this unit replaces (so a hand-written predecessor's line
                is stripped on sync, not left to double-fire); ONLY a claimed tag is touched

    ARCHITECTURE (data flow):
      jobs.d/*.json --load_units--> [specs] --compile_cron--> [tagged lines]
                                                                    |
      crontab -l --_read_crontab--> [current] --reconcile(strip own + claimed tags, keep every other
                                                            line, append desired)--> [new] --_write_crontab-->
"""
import fcntl
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import serve_dashboard as legacy   # _read_crontab / _write_crontab (proven crontab IO)
import smbos_lib as lib            # resolve_sop_dir (the canonical resolver; argv-free)

KINDS = ("job", "keychain-job")
UNIT_TAG_PREFIX = "# smbos-unit:"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# our cron lines END with `# smbos-unit:<name>` (compile_cron appends it). Match the TRAILING tag, not a
# substring, so a foreign line whose command merely MENTIONS the tag is never reaped.
_UNIT_LINE_RE = re.compile(re.escape(UNIT_TAG_PREFIX) + r"[a-z0-9][a-z0-9-]*$")
_CRON_SHORTCUTS = ("@reboot", "@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly")
_CLAIMS_RE = re.compile(r"^# [a-z0-9][a-z0-9._-]*$")   # a SPECIFIC tag, not a bare # or arbitrary text


class JobSpecError(Exception):
    """A malformed unit spec (surfaced to the caller; never written to the crontab)."""


def _plugin_jobs_d():
    return Path(__file__).resolve().parent.parent / "jobs.d"   # scripts/jobs.py -> <plugin>/jobs.d


def _has_line_break(s):
    """True if s holds any character that crontab round-tripping (str.splitlines) would split on
    (\\n \\r \\v \\f and friends). Such a char would fragment one cron entry into two on the NEXT sync,
    orphaning a line, so reject it. (A tab is fine -- splitlines does not break on it.)"""
    parts = str(s).splitlines()
    return len(parts) > 1 or (len(parts) == 1 and parts[0] != s)


def _validate(spec, where):
    """Reject anything that could corrupt the crontab: a bad name, a schedule that isn't exactly 5 cron
    fields or one @shortcut (extra tokens would shift the spec's command), a non-string/line-broken
    command, or a too-broad `claims` tag (would strip unrelated crontab lines)."""
    name = spec.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise JobSpecError(f"{where}: name must match [a-z0-9-] (got {name!r})")
    if spec.get("kind") not in KINDS:
        raise JobSpecError(f"{where}: kind must be one of {KINDS}, got {spec.get('kind')!r}")
    sched = spec.get("schedule")
    if not isinstance(sched, str) or _has_line_break(sched) or "#" in sched:
        raise JobSpecError(f"{where}: schedule must be a single cron line (no line break or #)")
    fields = sched.split()
    if not ((len(fields) == 1 and fields[0] in _CRON_SHORTCUTS) or len(fields) == 5):
        raise JobSpecError(f"{where}: schedule must be 5 cron fields or an @shortcut (got {sched!r})")
    if spec["kind"] == "job":
        cmd = spec.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise JobSpecError(f"{where}: a 'job' needs a non-empty string command")
        if _has_line_break(cmd):
            raise JobSpecError(f"{where}: command must be a single line (no embedded line break)")
    claims = spec.get("claims")   # optional: a legacy cron tag this unit migrates (strip + replace)
    if claims is not None and not (isinstance(claims, str) and _CLAIMS_RE.match(claims)):
        raise JobSpecError(f"{where}: 'claims' must be a specific tag like '# smbos-foo' (got {claims!r})")


def load_units(sop_dir):
    """Every unit spec from the PUBLIC plugin jobs.d, then the LOCAL <sop_dir>/jobs.d (private). A
    local spec OVERRIDES a public one of the same name. Raises JobSpecError on a bad/unparseable spec."""
    units = {}
    for d in (_plugin_jobs_d(), Path(sop_dir) / "jobs.d"):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                spec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise JobSpecError(f"{f}: {exc}")
            _validate(spec, f)
            units[spec["name"]] = spec
    return list(units.values())


def _cron_escape(s):
    return s.replace("%", r"\%")   # cron turns an unescaped % into a newline before the shell sees it


def compile_cron(units, uid):
    """Enabled units -> tagged crontab lines (PURE, no IO). A `job` runs its command directly; a
    `keychain-job` kickstarts its GUI agent so it runs in the keychain-bearing session. Each line is
    tagged `# smbos-unit:<name>` so the sync owns + reconciles exactly its own set."""
    lines = []
    for u in units:
        if not u.get("enabled", True):
            continue
        name = u["name"]
        if u["kind"] == "job":
            cmd = u["command"]
        else:  # keychain-job: cron can't read the keychain, so kickstart the GUI agent instead
            cmd = "/bin/launchctl kickstart -k gui/{}/com.smbos.{} >/dev/null 2>&1".format(uid, name)
        lines.append("{} {}  {}{}".format(u["schedule"], _cron_escape(cmd), UNIT_TAG_PREFIX, name))
    return lines


def reconcile(existing_lines, desired_lines, claimed_tags=()):
    """existing crontab lines + desired smbos lines -> the new crontab. Strips this manager's OWN lines
    (`# smbos-unit:`) AND any line ending with a tag a current unit CLAIMS (its `claims` field -- a
    hand-written predecessor it is migrating), then appends `desired`, PRESERVING every other line in
    order. ONLY claimed tags are touched, so cron lines owned by OTHER smbos installers (the digest, the
    dashboard watchdog) are never double-managed or reaped. Ownership is the TRAILING tag (end-of-line),
    not a substring, so a foreign line that merely mentions the tag survives. PURE (lists of strings)."""
    claimed = tuple(t.rstrip() for t in claimed_tags if t)
    def _managed(line):
        s = line.rstrip()
        return bool(_UNIT_LINE_RE.search(s)) or any(s.endswith(c) for c in claimed)
    keep = [l for l in existing_lines if not _managed(l)]
    return keep + list(desired_lines)


@contextmanager
def _crontab_lock(sop_dir):
    """Serialize the crontab read-modify-write across processes. `crontab -` is a full replace, so two
    concurrent syncs (or a sync racing another crontab writer) would last-writer-wins and drop lines."""
    f = open(Path(sop_dir) / ".jobs-sync.lock", "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def sync(sop_dir, dry_run=False):
    """Compile the registry + reconcile it into the crontab, under a lock. Returns (ok, message).
    NEVER writes a crontab it could not read (the safety invariant). dry_run returns the would-be text."""
    units = load_units(sop_dir)
    desired = compile_cron(units, os.getuid())
    claimed = [u["claims"] for u in units if u.get("claims")]   # legacy tags the units migrate
    with _crontab_lock(sop_dir):
        cur = legacy._read_crontab()
        if cur is None:   # crontab unavailable -> never write (the safety invariant)
            return False, "could not read the crontab; refusing to write (Full Disk Access?)"
        # note: on macOS an FDA-denied READ returns "" (not None), so this guard doesn't fire there --
        # but the write below then fails closed (crontab - is atomic), so the crontab stays untouched.
        new_lines = reconcile(cur.splitlines(), desired, claimed)
        text = "\n".join(new_lines) + ("\n" if new_lines else "")
        if dry_run:
            return True, text
        if legacy._write_crontab(text):
            return True, "synced {} unit(s)".format(len(desired))
        return False, "crontab write failed (Full Disk Access?)"


def sync_status(sop_dir):
    """Per-unit drift: is each spec's compiled cron line already live in the crontab? Returns
    {name: True|False|None} -- True = applied, False = a `jobs sync` is pending (the spec changed or was
    added, or a disabled unit still has a line), None = the crontab couldn't be read. READ-ONLY (never
    writes), so the FDA-less broker can call it; lets the dashboard show 'needs sync' instead of
    pretending a spec edit is already live."""
    units = load_units(sop_dir)
    cur = legacy._read_crontab()
    if not cur:                                      # None OR "" -- an FDA-denied read returns "" (not None) on
        return {u["name"]: None for u in units}      # macOS, and the broker is FDA-less; "" -> unknown, never a
                                                     # false "all pending" (a genuinely empty crontab reads unknown too, fine)
    def _name(line):                                 # the trailing `# smbos-unit:<name>` tag
        return line.rsplit(UNIT_TAG_PREFIX, 1)[1].strip()
    desired = {_name(l): l.rstrip() for l in compile_cron(units, os.getuid())}   # enabled units only
    live = {_name(s): s for s in (ln.rstrip() for ln in cur.splitlines()) if _UNIT_LINE_RE.search(s)}
    return {u["name"]: desired.get(u["name"]) == live.get(u["name"]) for u in units}


EDITABLE_FIELDS = ("schedule", "description", "enabled")
_CRON_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))   # min, hour, day-of-month, month, day-of-week


def _schedule_in_range(sched):
    """Each numeric cron field is within range, so an edit can't write a spec that won't install (e.g.
    hour 25). Accepts @shortcuts, *, ranges (a-b), steps (*/n), lists (a,b); rejects out-of-range numbers
    and */0. Named months/days aren't accepted here -- the edit UI is numeric (edit the file for those)."""
    fields = sched.split()
    if len(fields) == 1 and fields[0] in _CRON_SHORTCUTS:
        return True
    if len(fields) != 5:
        return False
    for field, (lo, hi) in zip(fields, _CRON_RANGES):
        for part in field.split(","):
            m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
            if not m or (m.group(2) is not None and int(m.group(2)) == 0):   # malformed, or a */0 step
                return False
            if m.group(1) != "*":
                nums = [int(x) for x in m.group(1).split("-")]
                if any(n < lo or n > hi for n in nums) or (len(nums) == 2 and nums[0] > nums[1]):
                    return False
    return True


def set_job_fields(sop_dir, name, fields):
    """Apply {schedule|description|enabled} edits to a LOCAL spec (<sop_dir>/jobs.d/<name>.json), validate,
    and write it atomically under the sync lock. Returns the updated spec. Raises JobSpecError on a bad
    name/field/value or if there's no editable local spec by that name. Never edits the plugin's shipped
    specs or the crontab -- the change goes live on the next `jobs sync`."""
    if not (isinstance(name, str) and _NAME_RE.match(name)):
        raise JobSpecError("invalid job name")
    extra = sorted(k for k in fields if k not in EDITABLE_FIELDS)
    if extra:
        raise JobSpecError("not editable: {}".format(", ".join(extra)))
    if "description" in fields and not isinstance(fields["description"], str):
        raise JobSpecError("description must be text")
    if "enabled" in fields and not isinstance(fields["enabled"], bool):
        raise JobSpecError("enabled must be true or false")
    path = Path(sop_dir) / "jobs.d" / (name + ".json")
    if not path.is_file():
        raise JobSpecError("no editable job named {!r}".format(name))
    with _crontab_lock(sop_dir):                     # serialize spec writes against a concurrent sync
        spec = json.loads(path.read_text(encoding="utf-8"))
        spec.update(fields)
        _validate(spec, str(path))                   # name/kind/5-field schedule/command/claims
        if "schedule" in fields and not _schedule_in_range(spec["schedule"]):
            raise JobSpecError("schedule has an out-of-range field")
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    return spec


CREATE_FIELDS = ("name", "kind", "schedule", "command", "description", "enabled")


def create_job(sop_dir, fields):
    """Create a new LOCAL job spec from {name, kind, schedule, command?, description?, enabled?}, validated
    and written to <sop_dir>/jobs.d/<name>.json. Raises JobSpecError on a bad/duplicate name or an invalid
    spec. Goes live on the next `jobs sync`."""
    name = fields.get("name")
    if not (isinstance(name, str) and _NAME_RE.match(name)):
        raise JobSpecError("name must be lowercase letters, numbers, or hyphens")
    extra = sorted(k for k in fields if k not in CREATE_FIELDS)
    if extra:
        raise JobSpecError("unknown field: {}".format(", ".join(extra)))
    if any(u["name"] == name for u in load_units(sop_dir)):       # name taken (local OR a shipped plugin job)
        raise JobSpecError("a job named {!r} already exists".format(name))
    desc = fields.get("description")
    if desc is not None and not isinstance(desc, str):
        raise JobSpecError("description must be text")
    spec = {"name": name, "kind": fields.get("kind"), "schedule": fields.get("schedule"),
            "enabled": bool(fields.get("enabled", True))}
    if fields.get("command") is not None:
        spec["command"] = fields["command"]
    if desc is not None:
        spec["description"] = desc
    _validate(spec, "new job")                                   # kind, 5-field schedule, command (for a job)
    if not _schedule_in_range(spec["schedule"]):
        raise JobSpecError("schedule has an out-of-range field")
    d = Path(sop_dir) / "jobs.d"
    path = d / (name + ".json")
    with _crontab_lock(sop_dir):
        if path.exists():                                        # a concurrent create won the race
            raise JobSpecError("a job named {!r} already exists".format(name))
        d.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    return spec


def delete_job(sop_dir, name):
    """Remove a LOCAL job spec (<sop_dir>/jobs.d/<name>.json). Raises JobSpecError on a bad name or if there
    is no local spec by that name. Its cron line is removed on the next `jobs sync`."""
    if not (isinstance(name, str) and _NAME_RE.match(name)):
        raise JobSpecError("invalid job name")
    path = Path(sop_dir) / "jobs.d" / (name + ".json")
    if not path.is_file():
        raise JobSpecError("no local job named {!r}".format(name))
    with _crontab_lock(sop_dir):
        path.unlink()
    return {"name": name}


def _sop_dir():
    # the canonical resolver ($SOP_DIR / ~/sops), NOT legacy.resolve_sop_dir -- that argv wrapper would
    # treat our subcommand ("sync" / "list") as an explicit SOP path (a ./sync dir would win).
    return lib.resolve_sop_dir(exit_on_missing=False) or Path.home() / "sops"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "sync":
        ok, msg = sync(_sop_dir(), dry_run="--dry-run" in argv)
        print(msg)
        return 0 if ok else 1
    if cmd == "list":
        for u in load_units(_sop_dir()):
            print("{:20} {:13} {}".format(u["name"], u["kind"], u["schedule"]))
        return 0
    print("usage: jobs.py {sync [--dry-run] | list}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
