import json
import subprocess
import sys
from datetime import datetime, timezone

from conftest import SCRIPTS

SCRIPT = SCRIPTS / "digest.py"


def build(library):
    r = subprocess.run([sys.executable, str(SCRIPT), "--sop-dir", str(library), "--print-only"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_empty_state(library):
    out = build(library)
    assert "Nothing is waiting for your approval." in out


def test_full_digest(library):
    now = datetime.now(timezone.utc).isoformat()
    pend = library / "pending"
    pend.mkdir()
    (pend / "x.md").write_text(
        "---\nsop: weekly-metrics-report\ntrigger_source: cron\ncreated: 2026-06-10T09:00:00Z\nstatus: pending\n---\nbody\n")
    q = library / "queue"
    q.mkdir()
    (q / "y.md").write_text(
        "---\nsop: send-invoice\nrequested: x\nsource: dashboard\nproject: /Users/me/acme\nstatus: queued\n---\n")
    w = library / "work"
    w.mkdir()
    (w / "z.md").write_text(
        "---\nid: z\ntitle: Onboard Acme\nstages: signed,kickoff\nstage: kickoff\nstatus: blocked\n---\n")
    (library / "runs.jsonl").write_text(
        json.dumps({"ts": now, "sop": "send-invoice", "result": "error", "cost_usd": 0.05,
                    "note": "API Error: OAuth token has expired"}) + "\n")
    (library / "triggers.json").write_text(json.dumps(
        {"monthly_budget_usd": 20.0,
         "triggers": [{"id": "t", "sop": "weekly-metrics-report", "spec": "cron(57 8 * * 1)",
                       "kind": "cron", "enabled": True}]}))
    out = build(library)
    assert "started by its schedule" in out                  # plain-language source
    assert "(in acme)" in out                            # queued with project name
    assert "Onboard Acme** is at **kickoff** (blocked)" in out
    assert "wasn't logged in" in out                         # failure translated
    assert "every Monday at 8:57 AM" in out                  # schedule humanized
    assert "cron(" not in out                                # no spec syntax anywhere
