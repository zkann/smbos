---
id: overdue-invoice-follow-up
title: Follow up on an overdue invoice
category: finance
triggers: chase the invoice, overdue invoice, payment reminder, they have not paid
run_inputs: which invoice (number or client)
version: 1
created: INSTALL-DATE
updated: INSTALL-DATE
last_used: never
runs: 0
clean_runs: 0
status: draft
source: library
---

# Follow up on an overdue invoice

## Purpose

Collect overdue payments without damaging the client relationship, using a consistent escalation ladder instead of ad-hoc nagging.

## When to use

An invoice is past its due date. NOT for invoices that are merely sent and pending.

## Inputs

- Invoice number, amount, due date, days overdue
- Payment and conversation history with this client

## Steps

1. Check how overdue the invoice is and whether the client has said anything about it.
2. Pick the escalation tier:
   - 1 to 7 days late: friendly nudge, assume oversight.
   - 8 to 21 days late: direct reminder with the invoice reattached and a specific ask ("can you confirm payment by Friday?").
   - 22+ days late: firm note from the owner personally; mention pausing work if relevant. [personalize: at what point do you pause work or add late fees?]
3. Draft the message in the matching tone.
4. **[APPROVAL]** Owner reviews anything at tier 2 or above.
5. Send, and log the touch in the invoice tracker.
6. Schedule the next check (one week out).

## My way

- [personalize: tone for tier 1: how casual are you with clients?]
- One follow-up per week maximum. Never multiple channels on the same day.
- Never threaten collections or legal action in writing without the owner saying so explicitly.

## Edge cases

- Client says payment was sent: thank them, verify before responding further, never imply doubt.
- Client raises a quality dispute in response: stop the collections thread and treat it as a support issue for the owner.

## Notes for next revision

## Changelog

- v1 (INSTALL-DATE): installed from the smbos starter library.
