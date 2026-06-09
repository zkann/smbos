---
id: weekly-metrics-report
title: Weekly metrics report
category: ops
triggers: weekly numbers, metrics report, how did we do this week
version: 3
created: 2026-04-14
updated: 2026-06-01
last_used: 2026-06-08
runs: 8
clean_runs: 3
status: trusted
---

# Weekly metrics report

## Purpose

A Monday-morning snapshot of the business: revenue, traffic, signups, churn. Goes in the ops journal and sets the week's priorities.

## When to use

Every Monday, or when the owner asks "how did we do this week". NOT for investor updates (those have their own SOP) and NOT for ad-hoc single-metric questions.

## Inputs

- Stripe dashboard access (MRR, new subscriptions, cancellations)
- PostHog (weekly active users, signup funnel)
- Google Search Console (clicks, impressions for the marketing site)

## Steps

1. Pull MRR, new subs, and cancellations from Stripe for the last 7 full days.
2. Pull WAU and signup conversion from PostHog, same window.
3. Pull GSC clicks and impressions, same window.
4. Compare every number to 4 weeks ago, not last week. (One week is noise.)
5. Draft the report using the format in My way.
6. **[APPROVAL]** Show the draft before saving anywhere.
7. Save to the ops journal under `journal/YYYY-MM-DD-weekly.md`.

## My way

- Compare against 4 weeks ago. Never week-over-week; it whipsaws.
- Lead with MRR. Always the first line.
- Round MRR to whole dollars, percentages to one decimal.
- Three sections max: Revenue, Usage, Marketing. No executive summary, no commentary section.
- Flag any metric that moved more than 15% in either direction with a one-line hypothesis. Otherwise no narrative.
- Plain markdown table for the numbers. No charts.

## Edge cases

- Stripe shows a refund spike: list the refunds individually with reasons, do not net them silently into MRR.
- A data source is down: report the other sections, mark the missing one "source unavailable", do not estimate.

## Notes for next revision

- Two runs in a row the owner asked for trial-to-paid conversion. Probably belongs in Steps as a fourth Revenue line.

## Changelog

- v3 (2026-06-01): compare window changed from week-over-week to 4-weeks-ago. Owner kept re-deriving it manually.
- v2 (2026-05-04): added refund handling edge case after the April refund spike got netted silently.
- v1 (2026-04-14): created.
