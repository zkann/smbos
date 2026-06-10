---
description: Track multi-stage work in progress (plan, build, review, ship)
argument-hint: "[list | start <title> | advance <id> | block <id> | done <id> | ...]"
---

Track in-flight multi-stage work: a feature being planned then built then reviewed then shipped, a client onboarding spanning days, a proposal moving to contract. A work item is an INSTANCE of a workflow; the SOP (or `[[sop:id]]` chain) is the template, the work item records where this particular piece sits.

Backed by `scripts/work.py` under the plugin root, storing one markdown file per item in `<sop-dir>/work/`. Route the user's plain words to it.

## What this is NOT

Don't reinvent a tool the user already has. If the work lives in a dedicated tracker (the user uses Linear for code tickets), let that own the stages; use a work item only for cross-cutting work with no home tool. When in doubt, ask whether it's already tracked somewhere.

## Routing

- "what's in flight" / list: `work.py list` (add `--all` to include done).
- "start tracking X" / new: `work.py new "Title" --stages "plan,build,review,ship" [--workflow <sop-id>] [--project <dir>]`. Infer sensible stages from the work if the user doesn't give them; for a code feature that's usually plan/build/review/ship. Set `--project` to the folder it belongs to (often the current directory) so it surfaces in the right sessions; omit for cross-project work.
- "move X to review" / advance: `work.py advance <id> "note"` (next stage) or `work.py stage <id> <stage> "note"` (jump). Always pass a short note on what happened.
- "X is blocked on Y": `work.py block <id> "Y"`; "unblock X": `work.py unblock <id>`.
- "X is done": `work.py done <id>`.
- log a detail without changing stage: `work.py note <id> "text"`.
- "where is X": `work.py show <id>`.

## How it connects to running SOPs

When you do a stage of an item's workflow (e.g. run `[[sop:work-ticket-to-merged-pr]]` for the build stage), advance the work item afterward with a note, so the tracker reflects reality. When the user starts a multi-stage piece of work that will clearly span sessions, offer to start tracking it. The session hook surfaces active items for the current folder at session start; the dashboard shows a stage board; the digest lists them under "In flight".

## Plain words

Render stages and status plainly. The work item file is the source of truth and is hand-editable; the user can also open `work/` in their editor.
