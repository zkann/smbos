#!/usr/bin/env python3
"""sop_contribution -- make per-SOP health visible so library drift can't stay silent.

A growing SOP/skill library degrades SILENTLY: accumulated, stale, or rarely-helping SOPs dilute
retrieval and drag end-task quality below the no-SOP baseline with no explicit error signal (the
"Library Drift" finding, arXiv 2605.19576, corroborated by SkillOps "skill technical debt"). The
defense is to surface each SOP's health from the counters the frontmatter already tracks, so a
library review acts on evidence instead of vibes.

The signal is `clean_runs`, which the SOP lifecycle defines as the CONSECUTIVE-clean streak (a run
with corrections or deviations resets it to 0; reaching 3 promotes an SOP to `trusted`). It is read
as a streak, NOT a lifetime ratio: an SOP with enough total runs whose streak has broken
(clean_runs == 0) is the one worth a look; a live streak is healthy regardless of total run count.

Conservative by construction (over-aggressive retirement is its own failure mode, known to push
performance below baseline): it only FLAGS for review, never recommends deletion, and stays
"insufficient-evidence" until an SOP clears a run floor. Read-only over the markdown frontmatter.

Usage:  python3 sop_contribution.py [--floor N] [sop_dir]   (sop_dir defaults to $SOP_DIR or ~/sops)
Stdlib only.
"""
import sys
from pathlib import Path

from smbos_lib import iter_sops, parse_frontmatter, resolve_sop_dir

EVIDENCE_FLOOR = 5          # below this many runs, do NOT judge (too little history; erosion guard)


def _int(val):
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def scan(sop_dir=None, floor=EVIDENCE_FLOOR):
    """One record per SOP carrying an `id`: id, status, runs, clean_runs (the consecutive-clean
    STREAK), and a conservative verdict (ok | REVIEW | insufficient-evidence | no-counter). SOP
    discovery and frontmatter parsing come from smbos_lib (iter_sops excludes the template, index,
    archive/, runtime dirs, and dotfiles); the `id` filter drops any remaining non-SOP markdown."""
    sop_dir = Path(sop_dir) if sop_dir else resolve_sop_dir(exit_on_missing=False)
    if not sop_dir:
        return []
    out = []
    for path in iter_sops(sop_dir):
        fm = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if "id" not in fm:
            continue
        runs, streak = _int(fm.get("runs")), _int(fm.get("clean_runs"))
        if runs is None or streak is None:
            verdict = "no-counter"
        elif runs == 0 or runs < floor:
            verdict = "insufficient-evidence"
        else:
            # clean_runs is a streak: 0 means the most recent run was NOT clean (corrections or
            # deviations) despite enough history -> worth a look. A live streak (>=1) is healthy.
            verdict = "REVIEW" if streak == 0 else "ok"
        out.append({"id": fm.get("id"), "file": str(path.relative_to(sop_dir)),
                    "status": fm.get("status", "?"), "runs": runs, "clean_runs": streak,
                    "verdict": verdict})
    return out


def report(records, floor=EVIDENCE_FLOOR):
    order = {"REVIEW": 0, "insufficient-evidence": 1, "no-counter": 2, "ok": 3}
    records = sorted(records, key=lambda r: (order.get(r["verdict"], 9), -(r["runs"] or 0)))
    lines = ["# Per-SOP clean streak (evidence floor = {} runs; flags only, never auto-retire)".format(floor), ""]
    lines.append("{:28} {:8} {:>5} {:>7}  {}".format("id", "status", "runs", "streak", "verdict"))
    for r in records:
        lines.append("{:28} {:8} {:>5} {:>7}  {}".format(
            (r["id"] or "?")[:28], (r["status"] or "?")[:8],
            "-" if r["runs"] is None else r["runs"],
            "-" if r["clean_runs"] is None else r["clean_runs"], r["verdict"]))
    review = [r for r in records if r["verdict"] == "REVIEW"]
    lines.append("")
    lines.append("REVIEW (enough runs but the clean streak is broken): {}".format(
        ", ".join(r["id"] for r in review) or "none"))
    lines.append("Note: REVIEW = a human should look (the latest run was not clean), NOT retire. "
                 "Retirement needs a high, separate evidence floor.")
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
