import json
import subprocess
import sys
from pathlib import Path

from conftest import SCRIPTS, make_sop

RUNNER = SCRIPTS / "run_sop.py"


def run(args, env, cwd=None):
    return subprocess.run([sys.executable, str(RUNNER)] + args,
                          capture_output=True, text=True, env=env, cwd=cwd, timeout=60)


def last_run(library):
    return json.loads((library / "runs.jsonl").read_text().splitlines()[-1])


def test_draft_refused_free(library, fake_claude):
    make_sop(library, id="draft-task", status="draft")
    r = run(["draft-task", "--sop-dir", str(library)], fake_claude)
    assert r.returncode == 1
    assert "Refused" in r.stderr + r.stdout
    rec = last_run(library)
    assert rec["result"] == "refused" and rec["cost_usd"] == 0


def test_missing_run_inputs_refused_free(library, fake_claude):
    make_sop(library, id="needs-stuff", status="active",
             extra="run_inputs: which client, what amount\n")
    r = run(["needs-stuff", "--sop-dir", str(library)], fake_claude)
    assert r.returncode == 1
    assert "needs inputs" in (r.stderr + r.stdout)
    assert last_run(library)["cost_usd"] == 0
    # with inputs supplied, the gate opens (fake claude runs at fake cost)
    r2 = run(["needs-stuff", "--sop-dir", str(library), "--inputs", "Acme, $5"], fake_claude)
    assert r2.returncode == 0
    assert last_run(library)["result"] == "ok"


def test_budget_guard(library, fake_claude):
    (library / "triggers.json").write_text(json.dumps({"monthly_budget_usd": 0.01}))
    from datetime import date
    (library / "runs.jsonl").write_text(json.dumps(
        {"ts": date.today().strftime("%Y-%m") + "-01T00:00:00+00:00", "cost_usd": 0.02}) + "\n")
    r = run(["weekly-metrics-report", "--sop-dir", str(library)], fake_claude)
    assert r.returncode == 1
    assert "budget" in (r.stderr + r.stdout).lower()
    assert last_run(library)["result"] == "skipped"


def test_ok_run_logs_cost(library, fake_claude):
    r = run(["weekly-metrics-report", "--sop-dir", str(library), "--source", "cron"], fake_claude)
    assert r.returncode == 0, r.stderr
    rec = last_run(library)
    assert rec["result"] == "ok"
    assert abs(rec["cost_usd"] - 0.0123) < 1e-9
    assert rec["source"] == "cron"


def test_unknown_sop(library, fake_claude):
    r = run(["nope", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0
    assert "No SOP" in (r.stderr + r.stdout)
