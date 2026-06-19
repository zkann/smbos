#!/usr/bin/env python3
"""miss_log -- the SmbOS "found miss" capture log (the miss-to-improvement loop).

A "miss" is a defect a HUMAN caught in SmbOS's own output: a duplicate task, a task with the wrong
due date, a status that no longer matches reality, a reminder that should have cleared. Capture is
the whole point: log it the MOMENT it is caught, as an EXTERNAL observation ("a human found X wrong
with Y"), so it can be triaged into a durable lowest-layer fix instead of hand-patched and forgotten.

Why the external-observation framing: the eval literature (Huang et al., ICLR 2024; the
"self-correction blind spot", Tsui 2025) shows an LLM reliably fixes an error handed to it as
external input but misses the same error in its own output. So a caught miss is recorded as a fact
about the output, never as "model, review yourself".

One module owns the schema so every writer uses the same shape. Each line is one miss. Stdlib only.

Schema (fields; absent = unknown):
  ts, ref (the offending item: an id or slug), title (one line: what was wrong), expected, actual,
  caught_by (default "human"), layer (set at triage: guard|schema|sop|prompt|memory|checkpoint),
  taxonomy (set at triage: the failure-bucket slug), status (open|triaged|fixed), fix_ref, why
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SOP_DIR = Path(os.environ.get("SOP_DIR", str(Path.home() / "sops")))
MISSES = SOP_DIR / ".miss-events.jsonl"   # SmbOS-level (cross-domain) miss log, beside the store
LAYERS = {"guard", "schema", "sop", "prompt", "memory", "checkpoint"}
STATUSES = {"open", "triaged", "fixed"}
ALLOWED = {
    "ref", "title", "expected", "actual", "caught_by", "layer", "taxonomy",
    "status", "fix_ref", "why",
}


def log_miss(title, path=MISSES, **fields):
    """Append one miss record. Unknown keys are dropped (the schema is the contract). `title` is the
    one-line external observation. Defaults: caught_by=human, status=open."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "title": str(title),
           "caught_by": fields.pop("caught_by", "human"),
           "status": fields.pop("status", "open")}
    for k, v in fields.items():
        if k in ALLOWED:
            rec[k] = v
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def read_misses(path=MISSES):
    """Parse the log, skipping malformed lines."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def report(misses):
    """Frequency-first error analysis (Husain/Shankar): count NOT-yet-fixed misses per taxonomy
    bucket, most frequent first -- the bucket that recurs is the one that earns a structural fix
    instead of another one-off patch. Also counts the fix layer each was routed to."""
    open_misses = [m for m in misses if m.get("status") != "fixed"]
    by_tax = Counter(m.get("taxonomy") or "(untriaged)" for m in open_misses)
    by_layer = Counter(m.get("layer") or "(unrouted)" for m in open_misses)
    lines = ["# Misses: {} open / {} total".format(len(open_misses), len(misses)), ""]
    lines.append("by taxonomy (frequency-first -- fix the top bucket structurally):")
    for tax, n in by_tax.most_common():
        lines.append("  {:>3}  {}".format(n, tax))
    lines.append("")
    lines.append("by fix layer:")
    for layer, n in by_layer.most_common():
        lines.append("  {:>3}  {}".format(n, layer))
    return "\n".join(lines) + "\n"


def _cli_append(argv):
    payload = argv[argv.index("--json") + 1] if "--json" in argv else sys.stdin.read()
    obj = json.loads(payload)
    title = obj.pop("title", None) or obj.pop("ref", "untitled miss")
    log_miss(title, **obj)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "append":
        _cli_append(sys.argv[2:])
    elif cmd == "report":
        sys.stdout.write(report(read_misses()))
    elif cmd == "list":
        for m in read_misses():
            if m.get("status") != "fixed":
                print("{}  [{:7}] {}".format(m.get("ts", "")[:10], m.get("status", "open"),
                                              m.get("title", "")))
    else:
        sys.exit("usage: miss_log.py {append [--json '<obj>' | <stdin>] | report | list}")
