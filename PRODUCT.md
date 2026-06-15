# PRODUCT.md

Jobs to be done for SmbOS, and the experience they imply. Written fresh: this starts from the small-business owner's day, not from the current dashboard. DESIGN.md describes the system we built; this describes the person we built it for and the ideal we should be aiming at. Where the two disagree, this is the target and DESIGN.md is the current state.

## Who this is for

A small-business owner who is also the business's bottleneck. A solo consultant, a three-person agency, a contractor, a shop owner. They do the billable work and run the company at the same time. They cannot afford an operations hire, so operations live in their head: the invoices to send, the leads to chase, the onboarding steps, the renewals, the weekly report nobody else will write.

Two facts drive everything:

1. **Attention is their scarcest resource.** Every minute spent on a dashboard, decoding a status, or babysitting a task is a minute stolen from the work that pays. A tool that adds management overhead loses, even if it automates real work.
2. **Their baseline emotion is low-grade "what am I forgetting."** The recurring operational stuff is exactly what slips when they are heads-down on a client. The fear is not a single dropped ball; it is not knowing whether one dropped.

So the product is not competing with other software. It is competing with the owner's own overloaded memory and the quiet anxiety that comes with it.

## The core job

> "Run my business's recurring operations the way I would, without it all depending on me being available."

The closest human analogy is hiring a capable operations manager. You show them how things are done here. They watch the calendar and handle the routine. They bring you only what needs your judgment. They ask before doing anything risky. They earn more rope as they prove themselves. They report back so you stay aware without staying involved.

That analogy, "an ops manager you train, who earns autonomy over time," is a sharper north star than "an operating system for your business." An OS is the architecture. An ops manager is the felt relationship, and it tells us how the product should behave: what it shows, when it interrupts, how it asks permission, how it grows.

## The jobs, decomposed

Each is stated in the owner's words, with the circumstance that triggers it and what makes them keep or drop the tool.

**1. Delegate the doing.** "Get this done the way I'd do it, without me doing every step." The owner has a way they invoice, onboard, follow up. They want that way preserved and executed, by someone other than them, consistently. The unique promise here is execution, not tracking: the thing actually gets done, in their style. Drop trigger: it does the task generically, not their way.

**2. Catch what would slip.** "Make sure nothing falls through the cracks." Renewals, follow-ups, month-end invoicing, the report. The job is vigilance the owner no longer has to supply. Emotionally this is the big one: it converts background dread into "it is handled." Drop trigger: something important slips anyway, or the tool nags about trivia.

**3. Protect my attention.** "Tell me the one thing only I can do, and handle the rest." The owner wants to glance, act on the short list that genuinely needs them, and close the tool reassured. The product's success is measured by how *little* lands on the owner, not how much it shows. Drop trigger: it surfaces everything and makes them triage.

**4. Let me hand off gradually, on my terms.** "Let it do more on its own as I learn to trust it." Nobody gives a new hire the keys on day one. The owner wants to start supervised, then let the tool prepare work for sign-off, then let it run unattended, capability by capability, with themselves holding the dial. Drop trigger: it acts more autonomously than they granted, or it never earns more and stays manual.

**5. Capture how I work, once.** "When I figure something out, remember it so I never re-figure it." The owner solves "how do we handle a refund / a difficult client / a rush order" once. They want that to become reusable without a documentation project. Drop trigger: capturing knowledge is its own chore.

**6. Improve as the business changes.** "Update how we do things when things change." Payment terms move to net-15, a new tool replaces an old one, a policy shifts. The procedures should absorb that from a passing comment, not a rewrite. Drop trigger: keeping it current is manual and falls behind reality.

**7. Never embarrass me or cost me.** "Don't let it send something half-baked to a client, overspend, or publish something wrong." The flip side of delegation. One bad autonomous action ends trust permanently. Safety is existential, not a feature. Drop trigger: a single runaway action, or even the credible fear of one.

**8. Reassure me it's worth it and under control.** "Show me the business ran, and that this pays for itself." Not a finance dashboard. A calm confirmation that the recurring operations happened, plus an honest sense of time saved against cost. Drop trigger: the value is invisible, so renewal feels optional.

## The owner's real rhythm

The owner does not experience their business as a library of procedures. They experience it as obligations in time and relationships with state:

- **Daily.** A morning scan (anything on fire, anything I owe today), client work, maybe an invoice or two, an end-of-day glance.
- **Weekly.** Follow-ups (did they pay, did the lead reply), a weekly report or check-in, planning, recurring marketing.
- **Monthly.** The invoicing cycle, a financial look, renewal and subscription checks, reporting to a partner or lender.
- **Event-triggered.** New client signs, onboarding. Project ends, wrap-up plus final invoice plus ask for a review. Lead arrives, qualify and chase. Something breaks, fix it.

In every case the owner thinks in terms of an outcome ("Acme needs to get paid"), a who ("the new client needs onboarding"), and a when ("follow up Thursday"). The procedure is the engine that produces the outcome. It is plumbing. The owner cares about the water.

## The reframe

This is the part the current product gets backwards, and the reason reorganizing panels has not felt like enough.

**Today the dashboard is organized around the system's machinery:** procedures and their run states, six panels named for internal stages. That exposes the engine. The owner has to translate "I need to get paid by Acme" into "find the invoice procedure, check its status, run it." The product asks the owner to think in its ontology.

**The ideal organizes around the owner's work, obligations, and their relationship with the assistant.** The procedure becomes mostly invisible, the engine under a result the owner actually wants. Three principles fall out:

- **Show outcomes, not machinery.** "Acme's invoice is ready to send," not "send-invoice (active) prepared an output." A procedure status is an implementation detail; surface it only in the training area.
- **Success is how little needs the owner.** The primary surface is an inbox of things needing the owner that should trend toward empty. A short or empty "your move" list is the product working, not the product being idle.
- **Be a colleague, not a console.** The tone, cadence, and permission model should read like notes from a trusted ops person, never a control panel of automation jobs.

## The ideal experience

### Shape: three surfaces, one relationship

The product already spans more than a dashboard. The ideal uses each surface for what it is best at:

- **Conversation (Claude Code).** Where work gets done, decided, and captured. The owner talks to the assistant: "send Acme's invoice," "what's overdue," "set up the new client," "remember how we just did that." This is the doing surface.
- **The Brief (the dashboard).** The ambient, glanceable state of operations plus the asynchronous inbox of what needs the owner. This is the staying-aware surface. It does not try to replicate the conversation; it is what the ops manager leaves on your desk.
- **The proactive push (digest and just-in-time nudges).** How the product stays alive in a heads-down owner's day. A short daily brief, and a timely ping only when something genuinely needs them. Attention-first: the bar for interrupting is high, and most things wait for the next brief.

A "your move" item should be resolvable straight from the Brief for the simple cases (one tap to approve or send), or hand off into a focused conversation for the cases that need discussion.

### The Brief, concretely

It reads like a standing note from a competent colleague, in this order, with each section appearing only when it has something to say:

```
SmbOS / Tuesday morning

  All clear. I handled 3 things since yesterday, nothing needs you.
  Acme's invoice goes out tomorrow.

  YOUR MOVE
  (empty most days; the only part that should ever feel urgent)

  HANDLING / HANDLED
  ✓ Sent the September invoice to Acme            yesterday
  ✓ Followed up with 2 leads                       yesterday
  ⟳ Preparing your weekly report                   ready ~3pm

  ON THE HORIZON
  Tomorrow   Invoice run (4 clients)
  Friday     Weekly report
  Next week  2 client renewals come due

  READY FOR MORE
  I've prepared the invoice 3 times and you approved each one
  unchanged. Want me to send it on my own from now on?  [Yes] [Not yet]

  This month: ran 31 tasks, saved you ~6 hours, cost ~$12 of $20.
```

When something does need the owner, "your move" carries it in plain outcome language with one or two clear actions:

```
  YOUR MOVE (2)
  • Acme's invoice ($4,200) is drafted and ready to send.
       [Send it]   [Change something]   [Not now]
  • The Bright Co proposal is stuck: it needs the scope you
    mentioned. [Give it the scope]   [I'll handle this later]
```

What each zone serves:

- **The one-line state** answers "am I okay" in two seconds. It is the whole product for the owner who only has two seconds.
- **Your move** is job 3 (protect attention). Finite, plain, actionable, trending empty.
- **Handling / handled** is jobs 2 and 8 (nothing slips, reassurance). Low visual weight, ambient. The receipts that let the owner relax.
- **On the horizon** is job 2 again, forward-looking: the obligations in time, the heartbeat of the business, proof nothing is unscheduled.
- **Ready for more** is job 4 (gradual hand-off): the trust-grant moments, surfaced only when earned.
- **The value line** is job 8: honest worth against cost, framed as time saved, not just dollars spent.

The procedure library and settings live one layer back. They are the training area, visited occasionally to teach or adjust, not the daily surface.

### The autonomy and trust model, redesigned

The current draft / active / trusted ladder is the right instinct (gradual delegation) wired the wrong way (status the system grants automatically, with autonomy meaning different things in different places). Replace it with a dial the owner controls, per capability:

- **With me.** Runs only when we do it together, live. The default for anything new or sensitive.
- **Prepare and ask.** The assistant does the prep on its own inside the safety boundary (it can research and draft, it cannot send, publish, or spend), and the result waits for the owner's one-tap approval before anything leaves.
- **On its own.** The assistant runs it unattended on its schedule or trigger and reports back after. Only for what the owner has blessed.

Two rules make this trustworthy:

1. **The assistant recommends; the owner grants.** After several clean runs the assistant proposes moving up a level ("I've prepared this three times and you approved each unchanged, want me to send it on my own?"). The owner decides. That moment of granting trust is deliberate, owner-controlled, and reversible at any time. It is the emotional core of job 4, and it should never happen by silent auto-promotion.
2. **Safety is orthogonal to autonomy.** The capability boundary (what the assistant is allowed to touch at all: never spends without a checkpoint, never emails a client without sign-off, never deletes) is separate from how closely the owner watches. Even "on its own" honors the hard boundaries. Separating "what it can do" from "how much I watch" removes the contradiction in the current model, where a brand-new draft could already be prepared autonomously while the ladder implied only trusted things run alone.

This directly serves job 7: the owner can grant real autonomy without ever fearing a runaway action, because the dangerous actions are gated independently of the autonomy level.

### Onboarding, reframed

The fastest way to lose this owner is to open with "now configure your procedures." They will not. The library should grow from real work:

- The first time the owner does a real task with the assistant ("help me invoice Acme"), the assistant offers afterward: "Want me to remember how we did this, so I can handle it next time?" A procedure is born from actual work, personalized from the first run.
- The empty state is an invitation to do one real thing together, not a setup checklist. Onboarding is the first task, not a project.
- A starter pack can seed ideas, but framed as "examples I can learn if you want them," never as the owner's own library with phantom progress.

This serves job 5 (capture by doing) and removes the setup tax that kills adoption.

### Voice and feel

The product's job is to lower anxiety, so it must never manufacture any. Plain outcomes in the owner's language. No internal jargon, no raw errors, no wall of caution color for what is simply the normal starting state. Failures read as what happened plus the one fix. Wins are acknowledged so the owner feels the business is handled. It should sound like a calm, competent colleague writing you a short note, because that is the relationship we are selling.

## Design principles (the distilled rules)

1. **Protect attention.** Measure success by how little reaches the owner. Default to not interrupting.
2. **Show outcomes, not machinery.** The owner sees results and obligations; the procedure and its status stay backstage.
3. **Never add anxiety.** Calm by default. The normal state is reassuring, not alarming.
4. **Safety is separate from autonomy, and never optional.** Hard boundaries hold at every autonomy level.
5. **The owner grants trust; the assistant earns the recommendation.** No silent auto-promotion to autonomy.
6. **Capture by doing, not by configuring.** Knowledge and setup come from real work.
7. **Be a colleague, not a console.** Cadence and tone of a trusted ops manager.

## Where today's product stands against this

Not a re-litigation, just the honest delta, so the gap is explicit:

- The dashboard is organized by the system's stages (six co-equal panels) rather than the owner's outcomes and obligations. Target: an inbox of "your move" plus a calm activity-and-horizon feed, framed in outcomes.
- Trust is an auto-granted status with inconsistent meaning. Target: an owner-held autonomy dial with safety gated separately, and trust granted on the assistant's recommendation.
- Onboarding implies setup and can show phantom progress. Target: learn by doing the first real task.
- The proactive surface (digest, nudges) is treated as an option. Target: it is primary, because a heads-down owner will not habitually open a dashboard.
- Cost shows as spend. Target: value (time saved) against a calm budget guardrail.

## Open decisions

These are genuine forks where I took a position; they are worth confirming before building toward them.

1. **Primary view: obligation/work-centric, not procedure-centric.** My recommendation, because the owner thinks in outcomes. The cost is a bigger departure from today's library-first dashboard.
2. **Trust: assistant recommends, owner grants.** My recommendation over auto-promotion, because control is the emotional core of delegation.
3. **Invest in the proactive surface as primary.** My recommendation, because adoption depends on the product reaching the owner where they already are.
4. **Positioning: "an ops manager you train" as the felt model,** with "operating system" kept as the architecture story, not the owner-facing pitch.
