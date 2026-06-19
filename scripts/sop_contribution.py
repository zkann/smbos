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
import sys
from pathlib import Path

from smbos_lib import iter_sops, parse_frontmatter, resolve_sop_dir

EVIDENCE_FLOOR = 5          # below this many runs, do NOT judge contribution (erosion guard)
LOW_CLEAN_RATIO = 0.5       # clean_runs/runs under this (with enough runs) -> REVIEW, never auto-retire


def _int(val):
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def scan(sop_dir=None, floor=EVIDENCE_FLOOR):
    """One record per SOP carrying an `id` in frontmatter: id, status, runs, clean_runs, and a
    conservative verdict (ok | REVIEW | insufficient-evidence | no-counter). SOP discovery and
    frontmatter parsing come from smbos_lib (iter_sops skips the template, index, archive, runtime
    dirs, and dotfiles); the `id` filter drops any remaining non-SOP markdown."""
    sop_dir = Path(sop_dir) if sop_dir else resolve_sop_dir(exit_on_missing=False)
    if not sop_dir:
        return []
    out = []
    for path in iter_sops(sop_dir):
        fm = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if "id" not in fm:
            continue
        runs, clean = _int(fm.get("runs")), _int(fm.get("clean_runs"))
        rel = str(path.relative_to(sop_dir))
        if runs is None or clean is None:
            verdict, ratio = "no-counter", None
        elif runs == 0 or runs < floor:   # runs==0 also guards a degenerate --floor 0 (no ZeroDivision)
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
        if i + 1 >= len(args):
            sys.exit("usage: sop_contribution.py [--floor N] [sop_dir]")
        floor = int(args[i + 1])
        del args[i:i + 2]
    sop_dir = args[0] if args else None
    sys.stdout.write(report(scan(sop_dir, floor), floor))
