#!/usr/bin/env python3
"""sop_contribution -- make per-SOP contribution visible so library drift can't stay silent.

A growing SOP/skill library degrades SILENTLY: accumulated, stale, or rarely-helping SOPs dilute
retrieval and drag end-task quality below the no-SOP baseline with no explicit error signal (the
"Library Drift" finding, arXiv 2605.19576, corroborated by SkillOps "skill technical debt"). The
defense is to surface each SOP's contribution from the run counters the frontmatter already tracks
(runs / clean_runs), so a library review acts on evidence instead of vibes.

Equally important: over-aggressive retirement is its OWN failure mode (harsh auto-retirement on thin
evidence drove performance below baseline). So this tool is conservative by construction: it only
FLAGS for human review, never recommends deletion, and emits "insufficient-evidence" until an SOP has
cleared a run floor. It changes nothing -- read-only over the markdown frontmatter.

Usage:  python3 sop_contribution.py [--floor N] [sop_dir]   (sop_dir defaults to $SOP_DIR or ~/sops)
Stdlib only.
"""
import os
import sys
from pathlib import Path

DEFAULT_SOP_DIR = Path(os.environ.get("SOP_DIR", str(Path.home() / "sops")))
EVIDENCE_FLOOR = 5          # below this many runs, do NOT judge contribution (erosion guard)
LOW_CLEAN_RATIO = 0.5       # clean_runs/runs under this (with enough runs) -> REVIEW, never auto-retire
SKIP_NAMES = {"MEMORY.md", "INDEX.md", "DIGEST.md", "_template.md", "PACKS.md"}


def _frontmatter(path):
    """Parse the leading --- ... --- block into a flat {key: value} dict (string values). Returns {}
    if there is no frontmatter. Deliberately tiny: SOP frontmatter is flat key: value, no nesting."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm


def _int(val):
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def scan(sop_dir=DEFAULT_SOP_DIR, floor=EVIDENCE_FLOOR):
    """One record per SOP markdown file with frontmatter: id, status, runs, clean_runs, and a
    conservative verdict (ok | REVIEW | insufficient-evidence | no-counter)."""
    out = []
    for path in sorted(Path(sop_dir).rglob("*.md")):
        if path.name in SKIP_NAMES:
            continue
        fm = _frontmatter(path)
        if "id" not in fm:
            continue
        runs, clean = _int(fm.get("runs")), _int(fm.get("clean_runs"))
        rel = str(path.relative_to(sop_dir))
        if runs is None or clean is None:
            verdict, ratio = "no-counter", None
        elif runs < floor:
            verdict, ratio = "insufficient-evidence", (clean / runs if runs else None)
        else:
            ratio = clean / runs
            verdict = "REVIEW" if ratio < LOW_CLEAN_RATIO else "ok"
        out.append({"id": fm.get("id"), "file": rel, "status": fm.get("status", "?"),
                    "runs": runs, "clean_runs": clean, "ratio": ratio, "verdict": verdict})
    return out


def report(records, floor=EVIDENCE_FLOOR):
    order = {"REVIEW": 0, "insufficient-evidence": 1, "no-counter": 2, "ok": 3}
    records = sorted(records, key=lambda r: (order.get(r["verdict"], 9), -(r["runs"] or 0)))
    lines = ["# Per-SOP contribution (evidence floor = {} runs; flags only, never auto-retire)".format(floor), ""]
    lines.append("{:28} {:8} {:>5} {:>6} {:>6}  {}".format("id", "status", "runs", "clean", "ratio", "verdict"))
    for r in records:
        ratio = "-" if r["ratio"] is None else "{:.2f}".format(r["ratio"])
        lines.append("{:28} {:8} {:>5} {:>6} {:>6}  {}".format(
            (r["id"] or "?")[:28], (r["status"] or "?")[:8],
            "-" if r["runs"] is None else r["runs"],
            "-" if r["clean_runs"] is None else r["clean_runs"], ratio, r["verdict"]))
    review = [r for r in records if r["verdict"] == "REVIEW"]
    lines.append("")
    lines.append("REVIEW (low clean ratio with enough runs): {}".format(
        ", ".join(r["id"] for r in review) or "none"))
    lines.append("Note: REVIEW = a human should look, NOT retire. Retirement needs a high, separate evidence floor.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    args = list(sys.argv[1:])
    floor = EVIDENCE_FLOOR
    if "--floor" in args:
        i = args.index("--floor")
        floor = int(args[i + 1])
        del args[i:i + 2]
    sop_dir = Path(args[0]) if args else DEFAULT_SOP_DIR
    sys.stdout.write(report(scan(sop_dir, floor), floor))
