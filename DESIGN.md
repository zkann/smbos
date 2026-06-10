# DESIGN.md

The dashboard's design system, extracted from the rendered product and locked in by /design-review on 2026-06-10. The dashboard is an APP UI (workspace, task-focused), not a marketing surface: calm hierarchy, few colors, dense but readable.

## Type

- System font stack (`-apple-system, system-ui, Segoe UI, Roboto, ...`). **Deliberate, not a default:** the product ships with zero dependencies and no network calls, so webfonts are out; the native stack reads as quiet macOS-grade chrome, which fits a tool that lives next to Terminal and Obsidian. Do not "upgrade" to a hosted font.
- Body 16px / 1.55. Microcopy floor 12px. Panel headings are 13px uppercase letterspaced labels (overline style); card titles 15.5px/600; the H1 is 21px/700.
- Numbers that line up in columns get `font-variant-numeric: tabular-nums` (add when a true table appears).

## Color

Warm neutrals plus three semantic hues, defined as CSS variables in the template root:

- Surfaces: `--bg #f7f7f5`, `--card #ffffff`, `--line #e4e4de`
- Ink: `--ink #1c1c1a`, `--muted #6f6f68`
- Status: draft = amber (`--draft-ink #92600a` on `#fdf3e3`), active = blue (`#1d4ed8` on `#e8f0fd`), trusted = green (`#15803d` on `#e6f4ea`), warnings `--warn #b4540a`
- Rule: status colors always ship with text labels, never color alone. Keep total non-gray palette under 15.

## Layout & spacing

- One content column, max-width 1180px, 32px page gutters; panels and cards on a 12px radius with 1px `--line` borders. No shadows except the modal.
- Panels are functional sections with one job each (inbox, plate, board, calendar); cards exist only when the card is the clickable object (a procedure). No decorative card grids.
- Today tab leads with what needs the owner; the library lives behind the Procedures tab.

## Interaction

- Buttons: primary = solid `--ink` on white text; secondary = 1px outline `.pbtn`. Minimum 30px tall on desktop, 44px on touch (`pointer:coarse`).
- Disabled run buttons stay fully legible (dashed outline, muted text), never opacity-faded into the background.
- Motion is minimal (120ms border/hover transitions) and fully disabled under `prefers-reduced-motion`.

## Voice (owner-facing copy)

Plain words, shared vocabulary: "waiting for you", "on your plate", "in flight", "coming up". Schedules as "every Monday at 8:57 AM", never cron syntax. Failures as what-happened plus one fix. No em dashes, no raw paths (home directory renders as `~`), SOP ids render as titles.
