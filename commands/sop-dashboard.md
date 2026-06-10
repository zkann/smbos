---
description: Open a visual dashboard of the SOP library (add --live for in-browser suggestions)
argument-hint: "[--live]"
---

Generate the visual dashboard and open it in the user's browser.

Two modes. Default is a static snapshot. Use live mode when `$ARGUMENTS` contains `--live` or the user wants to leave suggestions from the browser, keep the page current, or says "live".

## Live mode

1. Run the server in the background: `python3 <plugin-root>/scripts/serve_dashboard.py` (pass the SOP directory as an argument if standard resolution would pick the wrong one). It binds 127.0.0.1 on a random port with a per-run token.
2. Read the URL it prints (`http://127.0.0.1:<port>/?t=<token>`) and open it in the browser.
3. Tell the user, briefly: the page re-reads their files on refresh; the "Suggest a change" box saves into the SOP's notes; parked runs have Approve/Discard buttons (approve records the decision, the action happens in the next Claude session); non-draft SOPs have a "Run this now" button (background run, small automation cost, stops for approval); and any SOP can be queued for the next interactive session. Queued tasks are tagged with the folder the dashboard was launched from, so open the dashboard from a project's folder if you want its queued tasks to run there; from home they run anywhere. Say "stop the dashboard" to shut the server down.
4. When asked to stop, kill the background process.
5. Launch buttons ("Start in Claude", "Do it with Claude now") open the user's own terminal: auto-detected from the session that started the dashboard (Terminal.app or iTerm2), overridable with `sop_triggers.py terminal iterm`. If the user mentions using a different terminal app and launches open the wrong one, set that override. First-ever click may show a macOS permission prompt ("Python wants to control Terminal/iTerm").

## Static mode

### 1. Generate

The generator script ships with the plugin at `scripts/generate_dashboard.py` (the plugin root is the parent of the "Starter library:" path announced at session start; if unknown, locate it with `find ~/.claude/plugins -path '*smbos*' -name 'generate_dashboard.py' 2>/dev/null | head -1`).

Run it with python3:

```
python3 <plugin-root>/scripts/generate_dashboard.py
```

It resolves the SOP directory the standard way (`$SOP_DIR` > `./sops` > `~/sops`), writes `dashboard.html` into it, and prints the path. Pass the SOP directory as an argument if the standard resolution would pick the wrong one.

If python3 is not available, do the generation yourself: read `assets/dashboard-template.html` from the plugin, build the JSON array of `{path, content}` objects for every SOP file (skip `INDEX.md` and `_template.md`, include `archive/`), and substitute the `__SOPS_JSON__`, `__GENERATED__` (current UTC ISO timestamp), and `__SOP_DIR__` placeholders.

### 2. Open

Open the printed path in the default browser: `open <path>` on macOS, `xdg-open <path>` on Linux. If neither works, tell the user the file path to open manually.

### 3. Explain (first time only)

If this is the user's first dashboard, one or two sentences: it is a snapshot (regenerate any time with /sop-dashboard or by asking "show me my SOP dashboard"); the "Suggest a change" box copies a ready-made request to paste back into Claude Code, and changes go through the normal propose/approve flow. Everything stays on their machine; the page makes no network requests. Mention `--live` exists if they want suggestions saved directly.
