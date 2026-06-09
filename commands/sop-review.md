---
description: Audit the SOP library; find stale, drifted, overlapping, and missing SOPs
---

Audit and reorganize the user's SOP library. This is the periodic maintenance pass; suggest running it monthly.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`.

## 1. Read everything

Read every SOP in full, including archived ones (skim those). This review needs content, not just frontmatter.

## 2. Look for

- **Stale**: not used in 90+ days, or never used. Candidate for archive, or a sign the trigger phrases do not match how the user actually asks.
- **Draft graveyard**: status draft, installed or imported 30+ days ago, never run. Either the task never comes up (archive it) or it does come up and the SOP is not firing (fix the triggers, or schedule a first run now).
- **Drifted**: three or more changelog entries since the last structural rewrite, or accumulated "Notes for next revision" items, or internal contradictions between Steps and My way. Candidate for a clean rewrite that preserves the changelog.
- **Overlapping**: two SOPs with similar triggers or largely shared steps. Candidate for merge, or for a clear "When to use" boundary in each.
- **Bloated**: one SOP covering what is really two or three distinct workflows. Candidate for a split.
- **Missing**: recurring tasks visible in this conversation or in Notes sections that have no SOP. Candidate for /sop-new.

## 3. Report

Present a short findings report: one line per finding with a specific recommendation. No finding, no line; if the library is healthy, say so and stop.

## 4. Apply

Apply only what the user approves, one finding at a time:

- **Archive**: set `status: archived` in frontmatter, move the file to `archive/` (keep the category in the filename, e.g. `archive/finance--send-invoice.md`), remove its `INDEX.md` line. Never delete an SOP file; history is part of the product.
- **Merge/split/rewrite**: show the result before saving, bump versions, carry changelogs forward, note the restructure in each affected changelog, update `INDEX.md`.
- If the SOP directory is a git repo, commit once at the end with a summary of the review.
