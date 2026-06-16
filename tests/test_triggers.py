import subprocess
import sys

from conftest import SCRIPTS, make_sop

SCRIPT = SCRIPTS / "sop_triggers.py"


def run(args, library):
    import os
    env = dict(os.environ)
    env["SOP_DIR"] = str(library)
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True, env=env, timeout=30)


def test_add_enable_crontab_with_inputs(library):
    out = run(["add", "weekly-metrics-report", "cron(57 8 * * 1)"], library).stdout
    assert "added (disabled)" in out
    tid = out.split(": ")[1].strip()
    assert "enabled" in run(["enable", tid], library).stdout
    run(["set", tid, "inputs", "sources: Stripe only"], library)
    line = run(["crontab", tid], library).stdout
    assert line.startswith("57 8 * * 1 ")
    assert "--inputs 'sources: Stripe only'" in line
    assert "run_sop.py weekly-metrics-report" in line


def test_event_trigger_has_no_crontab(library):
    out = run(["add", "weekly-metrics-report", "linear.issue.created[label=x]"], library).stdout
    tid = out.split(": ")[1].strip()
    r = run(["crontab", tid], library)
    assert r.returncode != 0


def test_sync_from_frontmatter(library):
    make_sop(library, id="scheduled-thing", status="active",
             extra="on: cron(53 7 * * *)\n")
    out = run(["sync"], library).stdout
    assert "scheduled-thing--cron-53-7" in out
    listed = run(["list"], library).stdout
    assert "[off]" in listed and "scheduled-thing" in listed


def test_budget_roundtrip(library):
    assert "monthly_budget_usd = 33.0" in run(["budget", "33"], library).stdout
    assert "33.0" in run(["budget"], library).stdout


def test_costs_report(library):
    import json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    (library / "runs.jsonl").write_text(
        json.dumps({"ts": now, "sop": "a", "result": "ok", "cost_usd": 0.5}) + "\n"
        + json.dumps({"ts": now, "sop": "a", "result": "error", "cost_usd": 0.1}) + "\n")
    out = run(["costs"], library).stdout
    assert "This month: $0.60" in out
    assert "a: 2 runs" in out and "1 errors" in out


def test_list_tolerates_config_only_registry(library):
    # the dashboard's settings panel can create triggers.json with only config keys (no triggers
    # array); a list/sync must not KeyError on that partial file (cutover regression guard)
    (library / "triggers.json").write_text('{"launch_permission": "trust"}\n', encoding="utf-8")
    r = run(["list"], library)
    assert r.returncode == 0, r.stderr
    # add still works against the seeded-empty triggers list
    add = run(["add", "weekly-metrics-report", "cron(57 8 * * 1)"], library)
    assert add.returncode == 0, add.stderr
