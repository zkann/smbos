#!/usr/bin/env python3
"""Generate the SmbOS dashboard: a self-contained HTML view of the SOP library.

Usage: generate_dashboard.py [sop_dir]
SOP directory resolution: argv[1] > $SOP_DIR > ./sops > ~/sops
Writes <sop_dir>/dashboard.html and prints its path. No network, stdlib only.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SKIP_NAMES = {"INDEX.md", "_template.md"}


def resolve_sop_dir():
    candidates = []
    if len(sys.argv) > 1:
        candidates.append(Path(sys.argv[1]).expanduser())
    if os.environ.get("SOP_DIR"):
        candidates.append(Path(os.environ["SOP_DIR"]).expanduser())
    candidates.append(Path.cwd() / "sops")
    candidates.append(Path.home() / "sops")
    for c in candidates:
        if c.is_dir():
            return c
    sys.exit("No SOP directory found (checked argv, $SOP_DIR, ./sops, ~/sops). Run /sop-init first.")


def collect(sop_dir):
    files = []
    for p in sorted(sop_dir.rglob("*.md")):
        if p.name in SKIP_NAMES or p.name.startswith("."):
            continue
        rel = p.relative_to(sop_dir).as_posix()
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files.append({"path": rel, "content": content})
    return files


def ensure_gitignore(sop_dir):
    gi = sop_dir / ".gitignore"
    line = "dashboard.html"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if line not in existing.splitlines():
        with gi.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(line + "\n")


def main():
    sop_dir = resolve_sop_dir()
    template = Path(__file__).resolve().parent.parent / "assets" / "dashboard-template.html"
    html = template.read_text(encoding="utf-8")
    data = json.dumps(collect(sop_dir)).replace("</", "<\\/")
    html = html.replace("__SOPS_JSON__", data)
    html = html.replace("__GENERATED__", datetime.now(timezone.utc).isoformat())
    html = html.replace("__SOP_DIR__", str(sop_dir))
    out = sop_dir / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    if (sop_dir / ".git").exists():
        ensure_gitignore(sop_dir)
    print(out)


if __name__ == "__main__":
    main()
