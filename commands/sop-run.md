---
description: Execute a task following its SOP
argument-hint: "<sop name or task description>"
---

Execute a task by its SOP.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`.

## 1. Match

Read `INDEX.md` and match `$ARGUMENTS` against titles, descriptions, and trigger phrases. Fuzzy matching is fine; the user will not quote titles exactly.

- Multiple plausible matches: ask which one.
- No match: say so, name the closest SOPs if any are close, and offer to either do the task without an SOP (then capture it with /sop-new afterward) or pick one of the close matches.

## 2. Prepare

Read the full SOP file. Announce what you are running: id, version, status, and a one-line summary. Check the **Inputs** section and collect anything missing from the user before starting. Skim **Notes for next revision** so known rough edges do not surprise you mid-run.

If `status: draft`, personalize before executing: this SOP has never been verified by a real run. Resolve the `[personalize: ...]` slots that this run will actually touch by asking the user, write their answers into the file, and replace any remaining `INSTALL-DATE` placeholders with today's date. Slots the run does not touch can stay for later.

## 3. Execute

Work through **Steps** in order.

- The **My way** section overrides your defaults, even where your default seems better. If you believe a rule is wrong or outdated, raise it; never silently override.
- Stop and get sign-off at every **[APPROVAL]** step.
- Apply **Edge cases** when they hit.
- If a step cannot apply, say so in the moment, do the sensible thing, and remember it.

While executing, track every deviation: steps skipped or reordered, user corrections, missing inputs, tools that did not behave as documented, new edge cases.

## 4. Learn

After the task completes:

1. Update frontmatter: `last_used` to today, `runs` incremented. Clean run (no corrections, no deviations): increment `clean_runs`. Otherwise reset `clean_runs` to 0.
2. If there were deviations or corrections, propose a specific SOP edit as a before/after diff. Keep it minimal and targeted.
3. On approval: apply the edit, bump `version`, set `updated`, and add a dated changelog line stating what changed and why ("v4 (2026-06-09): send the draft before generating the PDF; owner wants to review copy first"). Update the SOP's `INDEX.md` line if its title, description, or triggers changed. A content edit resets `clean_runs` to 0 and returns a `trusted` SOP to `active`.
4. If the user declines but the observation matters, offer to record it under **Notes for next revision** instead.
5. Promote: a `draft` that just completed its first real run becomes `active` (personalization edits during the run do not block this). An `active` SOP whose `clean_runs` reached 3 becomes `trusted`; mention the promotion to the user in one line.
6. If the SOP directory is a git repo, commit the changes.

If the run was clean, just update the metadata and say the SOP held up.
