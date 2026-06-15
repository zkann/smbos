# DESIGN.md

The dashboard's design system, extracted from the rendered product and locked in by /design-review on 2026-06-10. The dashboard is an APP UI (workspace, task-focused), not a marketing surface: calm hierarchy, few colors, dense but readable.

## Type

- System font stack (`-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, ...`). **Deliberate, not a default:** the product ships with zero dependencies and no network calls, so webfonts are out; the native stack reads as quiet macOS-grade chrome, which fits a tool that lives next to Terminal and Obsidian. Do not "upgrade" to a hosted font.
- Body 16px / 1.55. Microcopy floor 12px, with one sanctioned exception: monospace overline labels and badges may sit at 11-11.5px because uppercase + letterspacing keeps them legible. Panel headings are the 11px mono overlines; card titles 15.5px/600; the H1 is 20px/650.
- Numbers that line up in columns get `font-variant-numeric: tabular-nums` (add when a true table appears).

## Color (Command Center, since 0.18.0)

shadcn zinc-dark tokens hand-ported to plain CSS (`assets/style.css` :root), fused with signal accents:

- Surfaces: `--background #09090b`, `--card #0f0f12`, `--card-raised #17171b`, `--border #27272a`
- Ink: `--foreground #fafafa`, `--muted-fg #a1a1aa`, `--subtle-fg #85858f` (AA-checked at 5.2:1)
- Primary signal: green `#22c55e` (live dot, current stage, progress, primary buttons with `#052e16` text)
- Status: draft = amber `#fbbf24`, active = blue `#60a5fa`, trusted = green `#4ade80`, each as soft translucent badges (10-12% tint + 25% border)
- Badges carry one meaning per color: `pending` (awaiting your approval) is amber like draft; `partial` (a prepared deliverable that came back incomplete) is a quiet neutral chip (`--card-raised` / `--muted-fg`), not amber, because it's a factual caveat rather than an attention state.
- Risk: red `--red #f87171` is reserved for danger, not status. It marks the lost-connection banner and the "skip approval" permission warning (`.setwarn`). Amber stays caution/draft; red stays "this removes a safeguard." Don't reuse red for a benign state.
- Secondary surfaces: `--chip-bg #18181b` (chips, tab rail), `--inset #0c0c0f` (sub-panels inside the dialog), `--border-strong #3f3f46` (hover borders, disabled dashes), `--primary-hover #1eb554`.
- Rules: dark surfaces gain elevation by lightness steps, not shadows; status colors always ship with text labels; zero counts render neutral, never tinted; every text/surface pair stays WCAG AA (verified in the 0.18.0 PR). No hex literals outside `:root`.
- Monospace (`ui-monospace`) marks the command-center DNA: panel labels (11px uppercase, .14em tracking), figures (counts, dollars), badges stay sans.

## Layout & spacing

- One content column, max-width 1180px, 32px page gutters; panels and cards on `--radius` (12px) with 1px `--border` borders.
- Radius scale: 14 dialog, 12 surfaces (panels, cards, banner), 10 tab container and inset sub-panels, 7 tab items (nested = outer minus gap), 6 controls and inline chips, 999 pills and badges.
- Spacing lands on even 4px-base steps; no odd one-off values.
- Shadows: the modal, the active tab's 1px lift, and the live dot's glow are the only three. Dark surfaces otherwise gain elevation by lightness steps (`--card` to `--card-raised`), never shadow.
- Panels are functional sections with one job each (inbox, plate, board, calendar); cards exist only when the card is the clickable object (a procedure). No decorative card grids.
- Today tab leads with what needs the owner; the library lives behind the Procedures tab.

## Interaction

- Buttons: primary = solid `--primary` green with dark text (shadcn recipe); secondary = 1px `--input` outline, transparent. Minimum 30px tall on desktop, 44px on touch (`pointer:coarse`). Focus = 2px `--ring` outline, offset 2px.
- Disabled run buttons stay fully legible (dashed outline, muted text), never opacity-faded into the background.
- Form controls (the footer Settings group): native `select`, `input[type=number]`, and `input[type=time]` share one recipe, transparent background, 1px `--input` border, 6px radius, the page system font (selects are explicitly in the `font:inherit` rule so they don't fall back to the browser default). The checkbox keeps native chrome tinted by `accent-color:var(--primary)`. Every control, including `select` and the Settings `<summary>` disclosure, gets the same 2px `--ring` focus outline as buttons, and meets the 44px touch target under `pointer:coarse`. Control sizing lives in style.css, no inline width/display on the rendered elements. Labels are always visible text, never placeholder-as-label.
- Motion is minimal (120ms border/hover transitions) and fully disabled under `prefers-reduced-motion`.

## Source structure

`assets/index.html` (document + data placeholders), `assets/style.css` (all tokens and component recipes), `assets/app.js` (render functions named 1:1 for future React components). The Python generator inlines all three into one self-contained file; the output stays single-file and zero-dependency even though the source is split.

## Voice (owner-facing copy)

Plain words, shared vocabulary: "waiting for you", "on your plate", "in flight", "coming up". Schedules as "every Monday at 8:57 AM", never cron syntax. Failures as what-happened plus one fix. No em dashes, no raw paths (home directory renders as `~`), SOP ids render as titles.
