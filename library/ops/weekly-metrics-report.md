---
id: weekly-metrics-report
title: Weekly metrics report
category: ops
triggers: weekly numbers, metrics report, how did we do this week, weekly report
version: 1
created: INSTALL-DATE
updated: INSTALL-DATE
last_used: never
runs: 0
clean_runs: 0
status: draft
source: library
---

# Weekly metrics report

## Purpose

A weekly snapshot of the business in a consistent format, so trends are visible and the week's priorities have numbers behind them.

## When to use

Once a week on a fixed day, or when the owner asks how the week went. NOT for investor updates or deep analyses.

## Inputs

- [personalize: your revenue source: Stripe, Shopify, QuickBooks, bank account?]
- [personalize: your traffic or usage source: Google Analytics, PostHog, GSC?]
- [personalize: your pipeline or orders source: CRM, order system?]

## Steps

1. Pull the last 7 full days from each source.
2. Compare each number to the same window 4 weeks ago. [personalize: or do you prefer a different comparison window?]
3. Draft the report in the standard format (see My way).
4. Flag any metric that moved more than 15% either way, with a one-line hypothesis. [personalize: different threshold?]
5. **[APPROVAL]** Show the draft before saving or sending.
6. Save or send it. [personalize: where does the report live: a journal file, Notion, an email to yourself?]

## My way

- [personalize: which single metric leads the report?]
- Three sections, one markdown table each. No executive summary, no padding.
- Round currency to whole dollars, percentages to one decimal.
- If a data source is down, mark that section "source unavailable". Never estimate.

## Edge cases

- Holiday weeks: note the holiday next to any affected comparison instead of explaining the dip in prose.

## Notes for next revision

## Changelog

- v1 (INSTALL-DATE): installed from the smbos starter library.
