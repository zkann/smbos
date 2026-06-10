#!/usr/bin/env python3
"""Track multi-stage work in progress: one markdown file per in-flight item.

A work item is an INSTANCE of a workflow (an SOP or chain is the template);
it records where that particular piece of work currently sits. Lives in
<sop-dir>/work/. Stdlib only.

Usage:
  work.py list [--all]
  work.py new "Title" [--stages "plan,build,review,ship"] [--workflow <sop-id>] [--project DIR]
  work.py show <id>
  work.py advance <id> ["note"]        move to the next stage
  work.py stage <id> <stage> ["note"]  jump to a named stage
  work.py note <id> "text"             append a log line
  work.py block <id> ["reason"] | unblock <id>
  work.py done <id> ["note"]
  work.py reopen <id>
"""
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smbos_lib import resolve_sop_dir, split_frontmatter

DEFAULT_STAGES = "plan,build,review,ship"


def sop_dir():
    return resolve_sop_dir(use_cwd=True)


def wdir(d):
    w = d / "work"
    w.mkdir(exist_ok=True)
    return w


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:50] or "item"


def parse(path):
    return split_frontmatter(path.read_text(encoding="utf-8"))


def write(path, meta, body):
    order = ["id", "title", "workflow", "stages", "stage", "status", "project", "created", "updated"]
    keys = [k for k in order if k in meta] + [k for k in meta if k not in order]
    fm = "\n".join(f"{k}: {meta[k]}" for k in keys)
    path.write_text(f"---\n{fm}\n---\n{body.rstrip()}\n", encoding="utf-8")


def find(d, wid):
    p = wdir(d) / f"{wid}.md"
    if p.is_file():
        return p
    for p in wdir(d).glob("*.md"):
        if parse(p)[0].get("id") == wid:
            return p
    sys.exit(f"No work item '{wid}'. Run `list`.")


def stamp(meta):
    meta["updated"] = datetime.now(timezone.utc).isoformat()


def log(body, line):
    today = date.today().isoformat()
    return body.rstrip() + f"\n- {today}: {line}\n"


def stage_bar(meta):
    stages = [s.strip() for s in meta.get("stages", "").split(",") if s.strip()]
    cur = meta.get("stage", "")
    out = []
    seen_cur = False
    for s in stages:
        if s == cur:
            out.append(f"[{s}]")
            seen_cur = True
        elif not seen_cur:
            out.append(f"✓{s}")
        else:
            out.append(s)
    return " > ".join(out) if out else cur


def cmd_list(d, show_all):
    items = []
    for p in sorted(wdir(d).glob("*.md")):
        meta, _ = parse(p)
        if not show_all and meta.get("status") == "done":
            continue
        items.append(meta)
    if not items:
        print("No work in progress. Start one with: work.py new \"...\"")
        return
    for m in items:
        flag = {"blocked": " [BLOCKED]", "done": " [done]"}.get(m.get("status"), "")
        proj = f"  ({Path(m['project']).name})" if m.get("project") else ""
        print(f"- {m.get('title', m.get('id'))}{flag}{proj}\n    {stage_bar(m)}")


def cmd_new(d, args):
    title = args[0]
    stages = arg_val(args, "--stages") or DEFAULT_STAGES
    workflow = arg_val(args, "--workflow") or ""
    project = arg_val(args, "--project") or ""
    first = [s.strip() for s in stages.split(",") if s.strip()][0]
    wid = slug(title)
    p = wdir(d) / f"{wid}.md"
    n = 2
    while p.exists():
        p = wdir(d) / f"{wid}-{n}.md"
        n += 1
    wid = p.stem
    now = datetime.now(timezone.utc).isoformat()
    meta = {"id": wid, "title": title, "workflow": workflow, "stages": stages,
            "stage": first, "status": "active", "project": project,
            "created": now, "updated": now}
    write(p, meta, f"\n## Log\n- {date.today().isoformat()}: started at '{first}'.\n")
    print(f"Created work item '{wid}' at stage '{first}'.")


def cmd_advance(d, wid, note):
    p = find(d, wid)
    meta, body = parse(p)
    stages = [s.strip() for s in meta.get("stages", "").split(",") if s.strip()]
    cur = meta.get("stage", "")
    if cur in stages and stages.index(cur) < len(stages) - 1:
        nxt = stages[stages.index(cur) + 1]
        meta["stage"] = nxt
        meta["status"] = "active"
        stamp(meta)
        line = f"advanced to '{nxt}'" + (f": {note}" if note else "")
        write(p, meta, log(body, line))
        print(f"{meta['title']}: now at '{nxt}'." + (f" ({note})" if note else ""))
    else:
        print(f"{meta['title']} is at the last stage '{cur}'. Use `done` to close it.")


def cmd_stage(d, wid, stage, note):
    p = find(d, wid)
    meta, body = parse(p)
    meta["stage"], meta["status"] = stage, "active"
    stamp(meta)
    write(p, meta, log(body, f"moved to '{stage}'" + (f": {note}" if note else "")))
    print(f"{meta['title']}: now at '{stage}'.")


def cmd_note(d, wid, text):
    p = find(d, wid)
    meta, body = parse(p)
    stamp(meta)
    write(p, meta, log(body, text))
    print("noted.")


def cmd_status(d, wid, status, note):
    p = find(d, wid)
    meta, body = parse(p)
    meta["status"] = status
    stamp(meta)
    verb = {"blocked": "blocked", "active": "unblocked", "done": "done"}[status]
    write(p, meta, log(body, verb + (f": {note}" if note else "")))
    print(f"{meta['title']}: {verb}.")


def cmd_show(d, wid):
    print(find(d, wid).read_text(encoding="utf-8"))


def arg_val(args, flag):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    d = sop_dir()
    cmd = a[0]
    if cmd == "list":
        cmd_list(d, "--all" in a)
    elif cmd == "new" and len(a) >= 2:
        cmd_new(d, a[1:])
    elif cmd == "show" and len(a) >= 2:
        cmd_show(d, a[1])
    elif cmd == "advance" and len(a) >= 2:
        cmd_advance(d, a[1], a[2] if len(a) > 2 else "")
    elif cmd == "stage" and len(a) >= 3:
        cmd_stage(d, a[1], a[2], a[3] if len(a) > 3 else "")
    elif cmd == "note" and len(a) >= 3:
        cmd_note(d, a[1], a[2])
    elif cmd == "block" and len(a) >= 2:
        cmd_status(d, a[1], "blocked", a[2] if len(a) > 2 else "")
    elif cmd == "unblock" and len(a) >= 2:
        cmd_status(d, a[1], "active", a[2] if len(a) > 2 else "")
    elif cmd == "done" and len(a) >= 2:
        cmd_status(d, a[1], "done", a[2] if len(a) > 2 else "")
    elif cmd == "reopen" and len(a) >= 2:
        cmd_status(d, a[1], "active", "reopened")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
