---
description: Update an SOP from feedback
argument-hint: "<sop name> [what to change]"
---

Apply feedback to an existing SOP.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`.

## 1. Locate

Match the SOP named in `$ARGUMENTS` against `INDEX.md` (titles, descriptions, triggers; fuzzy is fine). Ambiguous: ask. Read the full file.

## 2. Determine the change

- If `$ARGUMENTS` states the change, use it.
- Otherwise pull it from the recent conversation: corrections the user made, preferences they stated, steps that went differently than documented.
- If neither yields anything concrete, ask what should change.

## 3. Propose as a diff

Show the exact edit as before/after. Rules:

- Route the change first: is it UNIVERSAL or PROJECT-SPECIFIC? Universal edits go to the home/base SOP. Project-specific edits go to the project overlay in `./sops` (offer to create one with `extends: <id>` if missing) or to the matching `## Variants` entry. If it is ambiguous and both layers exist, ask.
- Minimal and targeted. Fold changes into existing sections; do not rewrite the whole SOP unless asked.
- Preferences and constraints go in **My way**. Process changes go in **Steps**. Exceptions go in **Edge cases**. Toolchain or per-stack differences go in **Variants**.
- If the change makes an existing line obsolete, remove it rather than stacking contradictions.
- If items in **Notes for next revision** are addressed by this edit, fold them in and remove them from the notes.

Write a one-line `deliverable:` naming exactly what the owner receives when it runs; if the SOP researches the web in background runs, declare `research_domains:` (and `research_reads:` for files outside the library). These are honored only on stamped SOPs.

## 4. Apply

On approval:

1. Apply the edit to the body, and set `updated` to today.
2. Finish with the bookkeeping command: `python3 <plugin-root>/scripts/sop_version.py bump <id> --note "<what changed and why>"`. It bumps `version`, adds the dated changelog line, refreshes the content fingerprint, resets `clean_runs`, and returns a `trusted` SOP to `active` (it changed, so it re-earns trust). Do not hand-edit `version`, the changelog, or `content_hash`.
3. Update the SOP's line in `INDEX.md` if title, description, or triggers changed.
4. If the SOP directory is a git repo, commit.

Confirm what changed and the new version number.
