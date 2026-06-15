# PRODUCT.md

What SmbOS is, who it serves, and the experience it should become. This started as a fresh-eyes vision and was corrected through a hard premise review; where this and DESIGN.md disagree, this is the target and DESIGN.md is the current state.

## What SmbOS is

SmbOS turns the recurring work of running a small operation into plain-markdown procedures that Claude can run, and gives you one place to see, manage, and act on them.

The dashboard is a single app with two co-equal jobs:

- **Act.** Run the next thing and see what needs you. Approvals, what is in flight, what is coming up, and a way to launch a run without retyping it.
- **Manage and understand.** A visual home for your operation: see your procedures organized, edit and harden them, set schedules and reminders, and tune how much each one runs on its own.

These are two zones of one app, not two products. You go there to set things up and to do the next thing, the same way you would with any operations tool. An earlier version of this doc treated the dashboard as a pure action surface and hid the procedure library; that was wrong. For the people who actually use this, seeing and managing the procedures is a primary reason to open it, so the library is first-class.

## Who it serves

- **Primary user, now: a technical operator** who already runs recurring work through Claude Code and wants a visual console over it instead of re-deriving each task by hand. This person reads and edits markdown comfortably, lives close to the terminal, and wants the tool to make their own operations legible and repeatable. The product earns its place when this person stops doing the work manually and runs it through SmbOS instead.
- **Eventual market: non-technical small-business owners.** The aspiration is that the same engine, with enough polish and enough push, serves an owner who would never open a terminal. That is the broader-market direction, and it shapes long-term choices, but it is the destination, not today's user. Designing only for that owner risks building for someone we cannot yet watch. Build for the real user first; let the owner version fall out of a tool that already works.

The mental model that travels well across both: an operations manager you train, who earns more autonomy over time. Internally it is an "operating system for your business"; that phrase is the architecture, not the pitch.

## Invocation: dashboard now, push later

The hardest part of any tool like this is getting a task to actually run with less effort than just doing it yourself. Two stages:

- **Now: the dashboard is the launcher.** Until push exists, you start runs from the dashboard, so "run this" has to genuinely execute and return a result, not bounce you back to doing it by hand. If the action zone is a button that dumps you back into manual work, the whole merge fails quietly.
- **Later: push takes over invocation.** A daily brief and timely nudges surface what needs you so you do not have to remember to open anything. The dashboard becomes the place you land and manage, not the thing you must check.

## The two zones, concretely

### Act

- One plain-language line at the top: what state things are in and whether anything needs you.
- The things needing you, finite and trending toward empty as more runs are trusted. Each carries a clear action, including run-from-here while the dashboard is still the launcher.
- What is handling or handled, as calm reassurance. What is coming up, the obligations on the horizon.
- Moments where a procedure has earned more autonomy and is offered it.

### Manage and understand

- The procedure library, first-class: every procedure, organized, searchable, with its status and history legible at a glance.
- Edit and harden procedures, resolve their personalization slots, see drift.
- Per-procedure autonomy and schedule settings live here.
- Global settings: budgets, terminal, the daily brief, notifications.
- Room to grow: over time this is where non-procedure operating knowledge lives too (coding practices and other reference docs), so the dashboard becomes the operations hub, not only an SOP runner.

## The autonomy and trust model

Replace an auto-granted status ladder with a dial the operator controls, per procedure:

- **With me.** Runs only when you do it together, live. The default for anything new or sensitive.
- **Prepare and ask.** It does the prep on its own inside the safety boundary (it can research and draft, it cannot send, publish, or spend), and the result waits for your one-tap approval before anything leaves.
- **On its own.** It runs unattended on its schedule or trigger and reports back after. Only for what you have blessed.

Two rules make this trustworthy:

1. **You grant; the tool earns the recommendation.** After several clean runs it proposes moving up a level; you decide, and you can move it back anytime. That moment of granting trust is deliberate and reversible, never a silent promotion.
2. **Safety is separate from autonomy.** The capability boundary (never spend, never message a client, never delete without a checkpoint) holds at every autonomy level. "How much it does on its own" and "what it is allowed to touch at all" are different dials.

The dial lives in the Manage zone; the grant-moments surface in the Act zone.

## Principles

1. **Show outcomes, and let me manage the machinery.** Lead with results and what needs you, and give a first-class place to see and edit the procedures behind them. Do not hide the machinery from someone who wants to manage it.
2. **The launcher must actually run.** While the dashboard is the way work starts, running from it has to beat doing it by hand.
3. **Success is how little needs you.** The action surface should trend toward empty as trust grows.
4. **Safety is separate from autonomy, and never optional.** Hard boundaries hold at every level.
5. **You grant trust; the tool earns the recommendation.** No silent promotion to autonomy.
6. **Calm by default.** The tool exists to reduce the sense of things slipping; it must never manufacture anxiety. Plain words, no jargon, the normal state reassuring.
7. **Capture by doing.** Procedures and setup come from real work, not a configuration project.

## Build sequence

Go deep on one before wide on all. The first build is a thin vertical slice: one real recurring task that works end to end across both zones, you can run it from the Act zone and edit, schedule, and tune it in the Manage zone, and running it through SmbOS is genuinely better than doing it manually. Once one task clears that bar, replicate the pattern. This keeps the run-loop real before UI is scaled around it.

## Open decisions

1. **Editing in-app vs visualize-only.** Do procedures get edited inside the dashboard, or does the dashboard visualize and manage while editing stays in markdown and Claude? Affects how much of an editor the Manage zone needs.
2. **How soon non-procedure docs.** Is the broader operations-knowledge hub (coding practices and other reference docs) a near-term need or a later expansion? Changes whether this is an SOP tool or a knowledge hub from the start.
3. **First slice.** Which single recurring task is the thin vertical slice that proves the merged loop.

## What changed from the first draft

The first version of this doc centered a non-technical small-business owner and an action-only "brief" that hid the procedure library. A premise review corrected the center: the real user today is a technical operator, the dashboard's job is a merge of action and management (with the library first-class), invocation is dashboard-now and push-later, and the non-technical owner is the eventual market rather than the current user. The autonomy and trust model and the calm-by-default principles carried over intact.
