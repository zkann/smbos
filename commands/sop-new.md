---
description: Capture a task as a new SOP
argument-hint: "[task description, or blank to capture the task just completed in this conversation]"
---

Create a new SOP in the user's SOP directory.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`. If none exists, run the /sop-init flow first.

## 1. Gather source material

- If `$ARGUMENTS` describes a task, that is the subject.
- Otherwise, distill the task the user and you just completed in this conversation. The conversation is the best source: it contains the actual steps taken AND every correction the user made along the way. Corrections are "My way" material.

## 2. Draft

Use `_template.md` in the SOP directory as the skeleton (fall back to the structure described in /sop-init if it is missing). Fill in:

- **id/title/category**: short, recognizable. File goes to `<category>/<id>.md`.
- **triggers**: the phrases the user actually says when they want this task ("send the invoice", "do the weekly numbers"). Write them how the user talks, not how a manual would.
- **Steps**: concrete and executable by a future AI session with no memory of today. Name exact tools, files, URLs, and accounts. Mark owner sign-off points with **[APPROVAL]**.
- **My way**: everything that differs from how a generic AI would do it. Tone, format, ordering, thresholds, things to never do. If this section is empty, the SOP is probably not worth having; push the user to articulate at least one preference.
- **Inputs**: what must be known or available before starting. If some of it is PER-RUN information only the owner can supply (which client, which file, amounts), also set frontmatter `run_inputs:` with that list; it gates unattended runs for free instead of letting them spawn, discover the gap, and park at cost. The items double as UI copy (the dashboard shows them as a "Tell it:" checklist), so keep each comma-separated item short and plain: "which client", not "the client relationship context needed for tone calibration".
- **Composition**: if a step is itself a workflow that exists (or deserves to exist) as its own SOP, reference it as `[[sop:that-id]]` instead of restating its steps. If this task usually consumes another SOP's output, set frontmatter `needs: that-id`; if another task usually follows, set `next: that-id`. One task per SOP; chains over monoliths.
- **Scope**: before saving, decide the layer. A task done the same way everywhere goes to the home library. A task specific to this project goes to `./sops`. A project-flavored version of an existing home SOP becomes an overlay (`./sops/<category>/<same-id>.md` with `extends: <id>`, delta sections only), NOT a near-duplicate. Small per-stack differences (TypeScript vs Python toolchains) become a `## Variants` section in one SOP, with each variant naming its detectable condition.

## 3. Fill gaps by asking, not guessing

Ask the user only about genuine gaps: approval points, hard constraints, edge cases you saw hints of. Two or three questions, not an interrogation.

## 4. Review and save

Show the full draft. Iterate until the user approves. Then:

1. Set status by grounding: if this SOP was distilled from a task actually completed in this conversation, it has survived a real run, so `status: active`. If it was written from a description of a task not performed here, `status: draft`; drafts may keep `[personalize: question]` slots for unknowns and get verified on first run.
2. Save to `<sop-dir>/<category>/<id>.md` with today's date in `created`/`updated`, `runs` set to 1 for active (0 for draft), `clean_runs: 0`.
3. Add one line to `INDEX.md` in the standard format: `- **Title** (category/file.md): one-line description | triggers: phrase, phrase`.
4. If the SOP directory is a git repo, commit the new SOP with a one-line message.

Confirm to the user what was saved and where.
