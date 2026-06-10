import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

SOP_TEMPLATE = """---
id: {id}
title: {title}
category: {category}
triggers: {triggers}
{extra}version: 1
created: 2026-06-01
updated: 2026-06-01
last_used: never
runs: {runs}
clean_runs: 0
status: {status}
---

# {title}

## Purpose
Test SOP.

## Inputs
- Something ambient.

## Steps
1. Do the thing.
2. **[APPROVAL]** Owner signs off.

## My way
- Plainly.

## Notes for next revision

## Changelog
- v1 (2026-06-01): created.
"""


def make_sop(sop_dir, id="weekly-metrics-report", title="Weekly metrics report",
             category="ops", triggers="weekly numbers, metrics report",
             status="active", runs="0", extra=""):
    p = Path(sop_dir) / category / f"{id}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(SOP_TEMPLATE.format(id=id, title=title, category=category,
                                     triggers=triggers, status=status,
                                     runs=runs, extra=extra), encoding="utf-8")
    return p


@pytest.fixture
def library(tmp_path):
    """A minimal SOP library with one active SOP and an index."""
    d = tmp_path / "sops"
    d.mkdir()
    (d / "INDEX.md").write_text("# SOP Index\n", encoding="utf-8")
    make_sop(d)
    return d


@pytest.fixture
def fake_claude(tmp_path):
    """A `claude` shim on PATH that emits the headless JSON envelope at zero cost."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "claude"
    shim.write_text(
        "#!/bin/sh\n"
        'echo \'{"total_cost_usd": 0.0123, "duration_ms": 42, '
        '"session_id": "test-session", "result": "did the thing", "is_error": false}\'\n',
        encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env.pop("SOP_DIR", None)
    return env
