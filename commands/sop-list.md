---
description: List all SOPs with status and health
---

Show the user their SOP library.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`. If none exists, suggest /sop-init.

## 1. Read state from disk, not just the index

List the actual `.md` files in the SOP directory (excluding `INDEX.md`, `_template.md`, and `archive/`), and read each file's frontmatter.

## 2. Present

Group by category. For each SOP show: title, status (draft / active / trusted), version, runs, last_used, and a flag where useful:

- **unverified draft**: status draft and created more than 30 days ago without ever running; suggest running it or archiving it
- **stale**: last_used more than 90 days ago, or never used and created more than 30 days ago
- **archived**: status is archived (only show these if the user asks)
- **pending notes**: has unaddressed items in "Notes for next revision"

Keep it to one line per SOP. End with totals and, if anything is flagged, a one-line suggestion (e.g. run /sop-review).

## 3. Repair the index

If `INDEX.md` disagrees with the files on disk (missing lines, lines for deleted files, stale descriptions or triggers), rebuild the out-of-sync lines and tell the user the index was repaired.
