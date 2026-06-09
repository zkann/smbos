---
description: Generate and open a visual dashboard of the SOP library
---

Generate the visual dashboard and open it in the user's browser.

## 1. Generate

The generator script ships with the plugin at `scripts/generate_dashboard.py` (the plugin root is the parent of the "Starter library:" path announced at session start; if unknown, locate it with `find ~/.claude/plugins -path '*smbos*' -name 'generate_dashboard.py' 2>/dev/null | head -1`).

Run it with python3:

```
python3 <plugin-root>/scripts/generate_dashboard.py
```

It resolves the SOP directory the standard way (`$SOP_DIR` > `./sops` > `~/sops`), writes `dashboard.html` into it, and prints the path. Pass the SOP directory as an argument if the standard resolution would pick the wrong one.

If python3 is not available, do the generation yourself: read `assets/dashboard-template.html` from the plugin, build the JSON array of `{path, content}` objects for every SOP file (skip `INDEX.md` and `_template.md`, include `archive/`), and substitute the `__SOPS_JSON__`, `__GENERATED__` (current UTC ISO timestamp), and `__SOP_DIR__` placeholders.

## 2. Open

Open the printed path in the default browser: `open <path>` on macOS, `xdg-open <path>` on Linux. If neither works, tell the user the file path to open manually.

## 3. Explain (first time only)

If this is the user's first dashboard, one or two sentences: it is a read-only snapshot (regenerate any time with /sop-dashboard or by asking "show me my SOP dashboard"); to change anything on it, just say so in plain words and the change goes through the normal propose/approve flow. Everything stays on their machine; the page makes no network requests.
