#!/usr/bin/env python3
"""SOP version integrity: detect, stamp, and bump.

The version field is only trustworthy if content can't change without it.
Each SOP carries a content_hash fingerprint of its procedure-bearing body
(journal sections excluded). An SOP whose body no longer matches its
fingerprint has "unrecorded changes": the dashboard flags it, the runner
refuses to run it unattended, and the session hook offers to reconcile.

Commands:
  check [--json]      list SOPs with unrecorded changes (silent when clean)
  stamp <id> | --all  record the current content as the current version
  bump <id> --note "" finish an approved edit: version+1, dated changelog
                      line, fresh fingerprint, trusted demoted to active,
                      clean-run streak reset

Stdlib only. SOP dir resolution: --sop-dir > $SOP_DIR > ~/sops.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smbos_lib import (content_fingerprint, find_sop, is_drifted, iter_sops,
                       resolve_sop_dir, set_frontmatter_fields, split_frontmatter)


def drifted_sops(sop_dir):
    out = []
    for p in iter_sops(sop_dir):
        meta, body = split_frontmatter(p.read_text(encoding="utf-8"))
        if is_drifted(meta, body):
            out.append({"id": meta.get("id", p.stem), "title": meta.get("title", p.stem),
                        "status": meta.get("status", "draft"),
                        "version": meta.get("version", "?"), "path": str(p)})
    return out


def cmd_check(sop_dir, as_json):
    items = drifted_sops(sop_dir)
    if as_json:
        import json
        print(json.dumps(items))
        return
    for it in items:
        line = f"{it['id']}: changed since v{it['version']} was recorded"
        if it["status"] == "trusted":
            line += " (trusted; it will not run unattended until the changes are recorded)"
        print(line)


def stamp_file(path):
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    path.write_text(set_frontmatter_fields(text, {"content_hash": content_fingerprint(body, meta)}),
                    encoding="utf-8")
    return meta


def cmd_stamp(sop_dir, sop_id, all_sops):
    if all_sops:
        n = 0
        for p in iter_sops(sop_dir):
            stamp_file(p)
            n += 1
        print(f"Recorded current content for {n} procedure{'s' if n != 1 else ''}.")
        return
    path = find_sop(sop_dir, sop_id)
    if not path:
        sys.exit(f"No SOP named '{sop_id}' found.")
    meta = stamp_file(path)
    print(f"{meta.get('title', sop_id)}: current content recorded as v{meta.get('version', '1')}.")


def add_changelog_line(body, line):
    marker = "## Changelog"
    if marker not in body:
        return body.rstrip("\n") + f"\n\n{marker}\n\n{line}\n"
    head, _, tail = body.partition(marker)
    # append at the end of the changelog section (before the next ## or EOF)
    nxt = tail.find("\n## ")
    if nxt == -1:
        return head + marker + tail.rstrip("\n") + "\n" + line + "\n"
    return head + marker + tail[:nxt].rstrip("\n") + "\n" + line + tail[nxt:]


def cmd_bump(sop_dir, sop_id, note):
    path = find_sop(sop_dir, sop_id)
    if not path:
        sys.exit(f"No SOP named '{sop_id}' found.")
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    try:
        new_version = int(meta.get("version", "1")) + 1
    except ValueError:
        sys.exit(f"version field is '{meta.get('version')}'; expected a whole number.")
    new_body = add_changelog_line(body, f"- v{new_version} ({date.today().isoformat()}): {note}")
    updates = {"version": new_version, "clean_runs": 0,
               "content_hash": content_fingerprint(new_body, meta)}
    demoted = meta.get("status") == "trusted"
    if demoted:
        updates["status"] = "active"
    rebuilt = set_frontmatter_fields(text, updates)  # ends with the old body verbatim
    head = rebuilt[:len(rebuilt) - len(body)] if body else rebuilt
    path.write_text(head + new_body, encoding="utf-8")
    title = meta.get("title", sop_id)
    msg = f"{title} is now v{new_version}."
    msg += (" It's back to active and needs 3 smooth runs to be trusted again."
            if demoted else " Its clean-run streak restarts.")
    print(msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sop-dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="list SOPs with unrecorded changes")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("stamp", help="record current content as the current version")
    s.add_argument("sop_id", nargs="?")
    s.add_argument("--all", action="store_true")
    b = sub.add_parser("bump", help="finish an approved edit")
    b.add_argument("sop_id")
    b.add_argument("--note", required=True, help="what changed and why (goes in the changelog)")
    args = ap.parse_args()

    sop_dir = resolve_sop_dir(explicit=args.sop_dir)
    if args.cmd == "check":
        cmd_check(sop_dir, args.json)
    elif args.cmd == "stamp":
        if not args.sop_id and not args.all:
            sys.exit("stamp needs an SOP id or --all")
        cmd_stamp(sop_dir, args.sop_id, args.all)
    elif args.cmd == "bump":
        cmd_bump(sop_dir, args.sop_id, args.note)


if __name__ == "__main__":
    main()
