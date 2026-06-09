---
id: send-invoice
title: Send an invoice
category: finance
triggers: send an invoice, invoice the client, bill them, time to invoice
version: 1
created: INSTALL-DATE
updated: INSTALL-DATE
last_used: never
runs: 0
clean_runs: 0
status: draft
source: library
---

# Send an invoice

## Purpose

Get a correct invoice to a client quickly, in the owner's standard format, with payment terms that match the agreement.

## When to use

Work is delivered (or a billing milestone hit) and the client owes money. NOT for estimates or proposals; those are sales documents.

## Inputs

- Client name and billing contact
- What is being billed: period or milestone, line items, amounts
- The agreement or rate that backs each line item

## Steps

1. Confirm the billing period or milestone and list the line items with amounts.
2. Check the numbers against the agreement or tracked hours. Flag anything that does not reconcile instead of guessing.
3. Draft the invoice in the invoicing tool. [personalize: which tool? Stripe, QuickBooks, Wave, a template doc?]
4. **[APPROVAL]** Show the owner the full invoice before it goes anywhere.
5. Send to the billing contact.
6. Record it: number, amount, due date. [personalize: where is the invoice tracker?]
7. Set a follow-up check for the due date.

## My way

- Payment terms: [personalize: net 15? net 30? due on receipt?]
- [personalize: any standard memo text, PO number requirements, or late-fee language?]
- Never send an invoice without owner approval, even a recurring one.
- Never round hours up; bill what was tracked.

## Edge cases

- Client disputes a line item: do not argue in writing; flag to the owner.
- Partial payment received earlier: show it as a credit line, not a reduced rate.

## Notes for next revision

## Changelog

- v1 (INSTALL-DATE): installed from the smbos starter library.
