# Starter library packs

This directory ships with the smbos plugin. Files here are TEMPLATES: they install with `status: draft`, contain `[personalize: ...]` slots, and must be personalized on first run before being followed.

## How to install SOPs from this library (instructions for the AI)

1. Copy each chosen file to the user's SOP directory, preserving the `category/` subdirectory.
2. Replace every `INSTALL-DATE` placeholder with today's date.
3. Leave `status: draft` as is. Drafts get personalized on their first run and promoted to `active` after it.
4. Add one INDEX.md line per installed SOP, in the standard format.
5. Tell the user: drafts are starting points. The first time each one runs, Claude will ask how THEY do it and fill in the `[personalize]` slots. Installing a pack takes a minute; personalizing happens gradually, one real task at a time.

Do not install the whole library. Install a pack (or a hand-picked subset); ten relevant SOPs beat fourteen generic ones.

## Packs by business type

**Consultant / freelancer / agency**
- clients/client-onboarding
- sales/write-proposal
- sales/lead-follow-up
- finance/send-invoice
- finance/overdue-invoice-follow-up
- clients/meeting-follow-up
- ops/weekly-metrics-report
- marketing/review-request

**SaaS / software product**
- ops/weekly-metrics-report
- ops/monthly-business-review
- clients/support-reply
- marketing/blog-post-publish
- marketing/email-newsletter
- marketing/social-media-post

**E-commerce / product seller**
- clients/support-reply
- marketing/email-newsletter
- marketing/social-media-post
- marketing/review-request
- finance/monthly-bookkeeping-prep
- ops/weekly-metrics-report

**Local / service business**
- sales/lead-follow-up
- finance/send-invoice
- finance/overdue-invoice-follow-up
- marketing/review-request
- marketing/social-media-post
- finance/monthly-bookkeeping-prep

If the user's business straddles types (most do), mix and match. Always show the chosen list and let the user add or drop SOPs before installing.
