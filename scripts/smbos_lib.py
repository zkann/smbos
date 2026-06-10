"""Shared SmbOS helpers: directory resolution, frontmatter, SOP iteration, run log.

The canonical implementations; scripts import from here instead of re-rolling.
Stdlib only, Python 3.9+ (the macOS system python that Claude Desktop uses).
"""
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


def append_run(sop_dir, record):
    with (Path(sop_dir) / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
