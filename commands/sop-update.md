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

- Minimal and targeted. Fold changes into existing sections; do not rewrite the whole SOP unless asked.
- Preferences and constraints go in **My way**. Process changes go in **Steps**. Exceptions go in **Edge cases**.
- If the change makes an existing line obsolete, remove it rather than stacking contradictions.
- If items in **Notes for next revision** are addressed by this edit, fold them in and remove them from the notes.

## 4. Apply

On approval:

1. Apply the edit, bump `version`, set `updated` to today.
2. Add a dated changelog line: what changed and why.
3. Reset `clean_runs` to 0; if the SOP was `trusted`, return it to `active` (it changed, so it re-earns trust).
4. Update the SOP's line in `INDEX.md` if title, description, or triggers changed.
5. If the SOP directory is a git repo, commit.

Confirm what changed and the new version number.
