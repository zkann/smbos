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

import serve_dashboard as legacy   # _read_crontab / _write_crontab / resolve_sop_dir (proven crontab IO)

KINDS = ("job", "keychain-job")
UNIT_TAG_PREFIX = "# smbos-unit:"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class JobSpecError(Exception):
    """A malformed unit spec (surfaced to the caller; never written to the crontab)."""


def _plugin_jobs_d():
    return Path(__file__).resolve().parent.parent / "jobs.d"   # scripts/jobs.py -> <plugin>/jobs.d


def _validate(spec, where):
    """Reject anything that could corrupt the crontab: a bad name (breaks the tag/label), or a
    newline/`#` in the schedule/command (would inject extra crontab lines or a fake tag)."""
    name = spec.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise JobSpecError(f"{where}: name must match [a-z0-9-] (got {name!r})")
    for k in ("kind", "schedule"):
        if not spec.get(k):
            raise JobSpecError(f"{where}: missing {k!r}")
    if spec["kind"] not in KINDS:
        raise JobSpecError(f"{where}: kind must be one of {KINDS}, got {spec['kind']!r}")
    sched = str(spec["schedule"])
    if "\n" in sched or "#" in sched:
        raise JobSpecError(f"{where}: schedule must be a single cron field (no newline or #)")
    if spec["kind"] == "job":
        cmd = spec.get("command")
        if not cmd:
            raise JobSpecError(f"{where}: a 'job' needs a command")
        if "\n" in str(cmd):
            raise JobSpecError(f"{where}: command must be a single line")
    claims = spec.get("claims")   # optional: a legacy cron tag this unit migrates (strip + replace)
    if claims is not None and (not isinstance(claims, str) or not claims.strip().startswith("#") or "\n" in claims):
        raise JobSpecError(f"{where}: 'claims' must be a single cron comment tag like '# smbos-foo'")


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
    dashboard watchdog) are never double-managed or reaped. PURE (lists of strings)."""
    claimed = tuple(t.rstrip() for t in claimed_tags if t)
    def _managed(line):
        s = line.rstrip()
        return (UNIT_TAG_PREFIX in s) or any(s.endswith(c) for c in claimed)
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
        if cur is None:
            return False, "could not read the crontab; refusing to write (Full Disk Access?)"
        new_lines = reconcile(cur.splitlines(), desired, claimed)
        text = "\n".join(new_lines) + ("\n" if new_lines else "")
        if dry_run:
            return True, text
        if legacy._write_crontab(text):
            return True, "synced {} unit(s)".format(len(desired))
        return False, "crontab write failed (Full Disk Access?)"


def _sop_dir():
    return legacy.resolve_sop_dir() if hasattr(legacy, "resolve_sop_dir") else Path.home() / "sops"


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
