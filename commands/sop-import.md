---
description: Convert existing process docs, a brain-dump, or past session history into draft SOPs
argument-hint: "<file path, URL, or pasted text> | interview | history"
---

Turn process knowledge the user already has into draft SOPs. Three modes; pick from `$ARGUMENTS`.

Resolve the SOP directory: `$SOP_DIR` if set, else `./sops` if it exists, else `~/sops`. If none exists, run the /sop-init flow first.

## Mode 1: Document (file path, URL, or pasted text)

Source can be anything with process knowledge in it: a Notion export, a Google Doc, a checklist, a section of an employee handbook, an old email explaining how something is done.

1. Read the source. Identify each distinct workflow in it; one doc often contains several.
2. Present the candidate list first (title + one line each). Let the user pick before drafting anything.
3. For each approved candidate, draft an SOP in the standard template. Map what the doc gives you; for gaps the doc does not answer, insert `[personalize: question]` slots rather than inventing answers.

## Mode 2: Interview (`interview`, or no source given)

For knowledge that lives only in the user's head.

1. Ask the user to pick ONE recurring task and explain how they do it as if training a new hire. Let them ramble; do not interrupt with structure.
2. Ask at most three follow-ups, prioritizing: approval points, hard "never do" rules, and what tools/accounts are involved.
3. Draft the SOP from the dump. Their phrasing of preferences goes into "My way" close to verbatim; it is already in their voice.
4. Offer to do another. Stop when the user stops.

## Mode 3: History (`history`)

Mine the user's past Claude Code sessions for recurring tasks that deserve SOPs.

1. Transcripts live in `~/.claude/projects/*/` as `.jsonl` files. Sample recent ones, for example: `ls -t ~/.claude/projects/*/*.jsonl | head -20`, then extract user-role message text from each (entries are one JSON object per line; user turns carry the user's request text).
2. Look for: the same task type requested more than once, repeated correction patterns (the user telling the AI the same preference twice is an SOP screaming to exist), and multi-step business tasks.
3. Present findings as a candidate list with evidence ("you asked for X on 3 occasions, and twice corrected the format the same way"). Let the user pick.
4. Draft each approved candidate. Corrections found in history go straight into "My way".
5. Privacy rule: quote the user's own words back only as evidence in this conversation; never copy credentials, client names, or message bodies into SOP files. Reference where things live instead.

## Saving (all modes)

Imported SOPs get `status: draft` (they have not survived a real run), today's date, `runs: 0`, `clean_runs: 0`, and a changelog line naming the source ("imported from onboarding-checklist.docx" / "imported from interview" / "imported from session history"). Save to `<category>/<id>.md`, add the INDEX.md line, and commit if the SOP directory is a git repo.

Close by telling the user: drafts get personalized and promoted the first time they run for real.
