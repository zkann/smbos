"""Shared SmbOS helpers: directory resolution, frontmatter, SOP iteration, run log.

The canonical implementations; scripts import from here instead of re-rolling.
Stdlib only, Python 3.9+ (the macOS system python that Claude Desktop uses).
"""
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

SKIP_NAMES = {"INDEX.md", "_template.md"}
# Directories under the SOP root that hold runtime state, never SOPs.
RUNTIME_DIRS = {"pending", "payloads", "triggers", "queue", "work"}
ARCHIVE_DIR = "archive"


def resolve_sop_dir(explicit=None, use_cwd=False, exit_on_missing=True):
    """argv-style explicit > $SOP_DIR > (optionally ./sops) > ~/sops."""
    candidates = [explicit, os.environ.get("SOP_DIR")]
    if use_cwd:
        candidates.append(str(Path.cwd() / "sops"))
    candidates.append(str(Path.home() / "sops"))
    for c in candidates:
        if c and Path(c).expanduser().is_dir():
            return Path(c).expanduser()
    if exit_on_missing:
        sys.exit("No SOP directory found (checked explicit, $SOP_DIR, ~/sops).")
    return None


def parse_frontmatter(text):
    """Return the frontmatter dict from a markdown document ('' values stripped)."""
    meta = {}
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta


def split_frontmatter(text):
    """Return (meta dict, body) for a markdown document."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = parse_frontmatter(text)
    return meta, m.group(2)


# Sections that are journals about the procedure, not the procedure itself.
# Excluded from the fingerprint so dashboard suggestions and changelog lines
# never read as unrecorded changes.
_JOURNAL_SECTIONS = ("Notes for next revision", "Changelog")


def content_fingerprint(body):
    """Hash of the procedure-bearing body: journal sections stripped, line endings normalized."""
    text = body.replace("\r\n", "\n")
    for name in _JOURNAL_SECTIONS:
        text = re.sub(rf"^## {re.escape(name)}\n.*?(?=^## |\Z)", "", text, flags=re.M | re.S)
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]


def is_drifted(meta, body):
    """True when the body no longer matches the recorded fingerprint.

    A missing fingerprint is "unstamped", not drift: existing libraries
    stay quiet until their SOPs are stamped or bumped.
    """
    recorded = meta.get("content_hash")
    return bool(recorded) and recorded != content_fingerprint(body)


def set_frontmatter_fields(text, updates):
    """Upsert frontmatter fields, preserving order; new fields go before the closing ---."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("document has no frontmatter")
    lines = m.group(1).splitlines()
    pending = dict(updates)
    for i, line in enumerate(lines):
        k = line.partition(":")[0].strip()
        if k in pending:
            lines[i] = f"{k}: {pending.pop(k)}"
    lines += [f"{k}: {v}" for k, v in pending.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + m.group(2)


def frontmatter_field(path, field, head_bytes=1000):
    """Read one frontmatter field from a file without parsing the whole document."""
    head = Path(path).read_text(encoding="utf-8")[:head_bytes]
    m = re.search(rf"^{re.escape(field)}: *(.+)$", head, re.M)
    return m.group(1).strip() if m else None


def iter_sops(sop_dir, include_archive=False):
    """Yield SOP file paths, skipping runtime dirs, index, template, dotfiles."""
    skip = set(RUNTIME_DIRS) if include_archive else set(RUNTIME_DIRS) | {ARCHIVE_DIR}
    for p in sorted(Path(sop_dir).rglob("*.md")):
        rel = p.relative_to(sop_dir)
        if p.name in SKIP_NAMES or p.name.startswith(".") or any(d in skip for d in rel.parts):
            continue
        yield p


def find_sop(sop_dir, sop_id):
    """Find an SOP by filename stem or frontmatter id; None if absent."""
    for p in iter_sops(sop_dir):
        if p.stem == sop_id:
            return p
        if frontmatter_field(p, "id") == sop_id:
            return p
    return None


def read_runs(sop_dir):
    """Parse runs.jsonl into a list of dicts, skipping malformed lines."""
    log = Path(sop_dir) / "runs.jsonl"
    out = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def month_spend(sop_dir):
    """Sum cost_usd of this calendar month's runs."""
    prefix = date.today().strftime("%Y-%m")
    total = 0.0
    for r in read_runs(sop_dir):
        if str(r.get("ts", "")).startswith(prefix):
            try:
                total += float(r.get("cost_usd") or 0)
            except (TypeError, ValueError):
                continue
    return total


def notify(title, body):
    """macOS notification; silent no-op elsewhere and on any failure."""
    if sys.platform != "darwin":
        return False
    esc = lambda s: str(s).replace("\\", "\\\\").replace('"', '\\"')
    try:
        import subprocess
        done = subprocess.run(["osascript", "-e",
                               f'display notification "{esc(body)}" with title "{esc(title)}"'],
                              capture_output=True, timeout=10)
        return done.returncode == 0
    except (OSError, Exception):
        return False


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _lock_holder(lock):
    """The pid recorded in a lockfile, or 0 when missing/corrupt."""
    try:
        return int(Path(lock).read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def run_lock_held(sop_dir, sop_id):
    """Read-only, stale-aware: is a LIVE run holding this SOP's lock?"""
    lock = Path(sop_dir) / "triggers" / f"{sop_id}.lock"
    return lock.exists() and _pid_alive(_lock_holder(lock))


def acquire_run_lock(sop_dir, sop_id):
    """One concurrent run per SOP, across every entry point (dashboard, cron, CLI).

    pid-bearing lockfile in the runtime dir; a lock whose pid is dead is stale
    and reclaimed (no deadlock after kill -9). Returns the lock path, or None
    if a live run already holds it.
    """
    locks = Path(sop_dir) / "triggers"
    locks.mkdir(exist_ok=True)
    lock = locks / f"{sop_id}.lock"
    for _ in range(3):  # O_EXCL makes acquisition atomic; loop covers stale reclaim
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()} {date.today().isoformat()}\n")
            return lock
        except FileExistsError:
            if _pid_alive(_lock_holder(lock)):
                return None
            lock.unlink(missing_ok=True)  # stale or corrupt; retry
    return None


def release_run_lock(lock):
    if lock:
        Path(lock).unlink(missing_ok=True)


def append_run(sop_dir, record):
    with (Path(sop_dir) / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
