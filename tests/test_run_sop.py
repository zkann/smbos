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


def test_drifted_sop_refused_free(library, fake_claude, tmp_path):
    from smbos_lib import content_fingerprint, read_runs, set_frontmatter_fields, split_frontmatter
    sop = library / "ops" / "weekly-metrics-report.md"
    text = sop.read_text()
    _, body = split_frontmatter(text)
    sop.write_text(set_frontmatter_fields(text, {"content_hash": content_fingerprint(body)}))
    # out-of-band edit after stamping
    sop.write_text(sop.read_text().replace("Do the thing.", "Wire money somewhere."))
    r = run(["weekly-metrics-report", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0
    assert "changed outside the normal save flow" in r.stderr
    last = read_runs(library)[-1]
    assert last["result"] == "refused" and last["cost_usd"] == 0
    assert "unrecorded changes" in last["note"]


def test_unstamped_sop_still_runs(library, fake_claude):
    r = run(["weekly-metrics-report", "--sop-dir", str(library)], fake_claude)
    assert r.returncode == 0


# ---------- prepare mode (background-first) ----------

def make_recording_claude(tmp_path):
    """A claude shim that records its argv and emits the JSON envelope."""
    import os, stat
    bindir = tmp_path / "recbin"; bindir.mkdir(exist_ok=True)
    argv_file = tmp_path / "claude-argv.txt"
    shim = bindir / "claude"
    shim.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > " + str(argv_file) + "\n"
                    "echo '{\"total_cost_usd\": 0.01, \"duration_ms\": 5, "
                    "\"session_id\": \"t\", \"result\": \"done\", \"is_error\": false}'\n")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env.pop("SOP_DIR", None)
    return env, argv_file


def test_prepare_runs_drafts_and_builds_the_cage(library, tmp_path):
    from smbos_lib import read_runs
    env, argv_file = make_recording_claude(tmp_path)
    make_sop(library, id="draft-prep", status="draft",
             extra="research_domains: example.com\ndeliverable: a test artifact\n")
    import subprocess, sys as _sys
    subprocess.run([_sys.executable, str(SCRIPTS / "sop_version.py"),
                    "--sop-dir", str(library), "stamp", "draft-prep"], capture_output=True)
    r = run(["draft-prep", "--prepare", "--sop-dir", str(library)], env)
    assert r.returncode != 0  # no artifact parked -> error (the shim parks nothing)
    argv = argv_file.read_text()
    assert "--setting-sources" in argv and "dontAsk" in argv
    assert "acceptEdits" not in argv
    assert "WebFetch(domain:example.com)" in argv  # stamped -> domains honored
    assert '"Bash"' in argv and '"WebSearch"' in argv and '"mcp__*"' in argv
    assert "///" not in argv  # the triple-slash grammar bug stays dead
    last = read_runs(library)[-1]
    assert last["result"] == "error" and "no artifact parked" in last["note"]


def test_prepare_unstamped_gets_no_domains(library, tmp_path):
    env, argv_file = make_recording_claude(tmp_path)
    make_sop(library, id="unstamped-prep", status="draft",
             extra="research_domains: example.com\n")
    run(["unstamped-prep", "--prepare", "--sop-dir", str(library)], env)
    assert "WebFetch(domain:" not in argv_file.read_text()


def test_prepare_gate_matrix(library, fake_claude, tmp_path):
    from smbos_lib import read_runs
    # personalize slots -> refused free
    p = make_sop(library, id="slotted", status="draft")
    p.write_text(p.read_text().replace("Do the thing.", "Do [personalize: how?] now."))
    r = run(["slotted", "--prepare", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0 and "personalize" in r.stderr.lower()
    assert read_runs(library)[-1]["cost_usd"] == 0
    # drift -> still refused in prepare
    import subprocess, sys as _sys
    q = make_sop(library, id="drifty", status="draft")
    subprocess.run([_sys.executable, str(SCRIPTS / "sop_version.py"),
                    "--sop-dir", str(library), "stamp", "drifty"], capture_output=True)
    q.write_text(q.read_text().replace("Do the thing.", "Changed."))
    r = run(["drifty", "--prepare", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0 and "normal save flow" in r.stderr
    # missing inputs -> still refused in prepare
    make_sop(library, id="needy", status="draft", extra="run_inputs: which client\n")
    r = run(["needy", "--prepare", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0 and "needs inputs" in r.stderr
    # --prepare + --force -> argparse error
    r = run(["needy", "--prepare", "--force", "--sop-dir", str(library)], fake_claude)
    assert r.returncode == 2 and "cannot be combined" in r.stderr


def test_run_lock_blocks_and_reclaims(library, fake_claude):
    import os
    from smbos_lib import read_runs
    locks = library / "triggers"; locks.mkdir(exist_ok=True)
    lock = locks / "weekly-metrics-report.lock"
    lock.write_text(f"{os.getpid()} live\n")  # this test process is alive
    r = run(["weekly-metrics-report", "--sop-dir", str(library)], fake_claude)
    assert r.returncode != 0 and "already running" in r.stderr
    assert read_runs(library)[-1]["note"] == "already running"
    for corrupt in ("999999 dead\n", "", "garbage\n", "-1 x\n", "0\n"):
        lock.write_text(corrupt)  # stale or corrupt -> reclaimed, run proceeds
        r = run(["weekly-metrics-report", "--sop-dir", str(library)], fake_claude)
        assert r.returncode == 0, corrupt
    assert not lock.exists() or lock.read_text().split()[0] not in ("999999", "garbage", "-1", "0")


def test_build_prompt_contracts():
    import run_sop as rs
    class A: sop_id = "x"; source = "cron"
    prep = rs.build_prompt("prepare", A, "/p/x.md", "park: write to /p/pending/f.md (...)",
                           "", "", "- inputs clause\n", deliverable="a list")
    trig = rs.build_prompt("triggered", A, "/p/x.md", "park: write to /p/pending/f.md (...)",
                           "", "", "- inputs clause\n")
    assert "NO externally visible action" in prep and "empty result is a result" in prep
    assert "partial: true" in prep and "a list" in prep
    assert "[APPROVAL]" in trig
    for shared in ("My way", "Plain words"):
        assert shared in prep and shared in trig


def test_notify_and_lock_helpers(monkeypatch, tmp_path):
    import smbos_lib as lib
    calls = []
    class Done:
        returncode = 0
    monkeypatch.setattr(lib, "os", lib.os)
    import subprocess as sp
    monkeypatch.setattr(sp, "run", lambda cmd, **kw: (calls.append(cmd), Done())[1])
    monkeypatch.setattr(lib.sys, "platform", "darwin")
    assert lib.notify("T", 'say "hi"') is True
    assert "osascript" in calls[-1][0] and '\\"hi\\"' in calls[-1][-1]
    monkeypatch.setattr(lib.sys, "platform", "linux")
    assert lib.notify("T", "b") is False
    lock = lib.acquire_run_lock(tmp_path, "abc")
    assert lock and lib.acquire_run_lock(tmp_path, "abc") is None  # held by live pid
    lib.release_run_lock(lock)
    assert lib.acquire_run_lock(tmp_path, "abc") is not None
