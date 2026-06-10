---
description: Set up the SOP directory, index, and template, and seed a starter pack
argument-hint: "[optional path, e.g. ~/sops or ./sops]"
---

Set up the user's SOP library.

## 1. Pick a location

- If `$ARGUMENTS` gives a path, use it.
- Otherwise: business workflows usually belong in `~/sops` (they follow the owner across projects). If the current directory is a dedicated ops/business workspace, `./sops` also makes sense. Ask the user which they want, with `~/sops` as the recommended default. Mention that `$SOP_DIR` can override the location later.

## 2. Create the structure

Create the directory plus two files:

`INDEX.md`:

```markdown
# SOP Index

One line per SOP. Keep in sync with the files on disk.
Line format: `- **Title** (category/file.md): one-line description | triggers: phrase, phrase`

(no SOPs yet)
```

`_template.md`:

```markdown
---
id: kebab-case-id
title: Human-readable title
category: ops
triggers: phrase one, phrase two
# needs: upstream-sop-id (optional; this SOP consumes that one's output)
# next: follow-on-sop-id (optional; what typically runs after)
# extends: home-sop-id (optional; only in project ./sops overlays: delta sections over the home SOP)
# run_inputs: which client, what is being billed (optional; per-run info an UNATTENDED run must have; gates triggered runs for free before any model spawns)
version: 1
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_used: never
runs: 0
clean_runs: 0
status: draft
---

# Title

## Purpose
One or two sentences: what this produces and why it matters.

## When to use
When this applies, and when it does NOT.

## Inputs
What is needed before starting: files, data, credentials, decisions only the owner can make.

## Steps
1. ...
2. ...

Mark any step that needs owner sign-off with **[APPROVAL]**.

## My way
The owner-specific rules that override AI defaults: tone, formats, tools, ordering, hard "never do" constraints. This section is the reason the SOP exists.

## Edge cases
Known exceptions and what to do about them.

## Notes for next revision
Observations from runs that have not been folded into the steps yet.

## Changelog
- v1 (YYYY-MM-DD): created.
```

Status lifecycle (record this in how you explain the system): `draft` = unverified, gets personalized on first run; `active` = survived a real run; `trusted` = 3+ consecutive clean runs (tracked in `clean_runs`); `archived` = retired, lives in `archive/`. Content edits reset `clean_runs` and return trusted SOPs to active.

SOPs live in category subdirectories (e.g. `finance/send-invoice.md`). Create category directories on demand, not up front.

SOPs compose: a step can execute another SOP inline with `[[sop:that-id]]`; frontmatter `needs:` names upstream SOPs whose output this one consumes; `next:` names typical successors. Prefer chains of small SOPs over one monolith.

SOPs adapt to context two ways. Small per-stack differences live in an optional `## Variants` section inside one SOP, each variant naming a detectable condition ("TypeScript projects (package.json present)"). Whole-project personalities live as overlays: a project's `./sops/<category>/<same-id>.md` with `extends: <home-id>` containing only the sections that differ; overlay sections replace the base's, except My way, which appends. The home library (`~/sops`) and a project's `./sops` are active together, project shadowing home by id.

## 3. Version history

If the SOP directory is not inside a git repo, offer to `git init` it. Version history is part of the transparency story: every SOP change is reviewable and revertible.

## 4. Seed a starter pack

The plugin ships a starter library (path announced at session start as "Starter library:"; if unknown, locate it with `find ~/.claude/plugins -path '*smbos*' -name 'PACKS.md' 2>/dev/null | head -1`).

1. Ask what kind of business the user runs: consultant/agency, SaaS, e-commerce, or local/service. Mixes are normal.
2. Read `PACKS.md` in the library and propose the matching pack as a checklist. Let the user add or drop SOPs before installing.
3. Install per the PACKS.md instructions: copy files preserving category directories, replace `INSTALL-DATE` with today, keep `status: draft`, add INDEX.md lines.
4. Set expectations in one sentence: these are drafts in a generic shape; the first time each one runs, you will ask how THEY do it and fill in the `[personalize]` slots.

If the user has existing process docs (Notion, Google Docs, checklists) or wants to capture from their own head instead, point them at /sop-import; both paths can coexist.

## 5. Wrap up

Tell the user the SOP index loads automatically at the start of every session, so new SOPs become active on the next session (or immediately in this one, since you now know about them). Suggest the easiest first win: next time they do any recurring task, just do it here and let the matching SOP run (or get captured).
