import threading

from conftest import make_sop

import smbos_lib as lib


def test_dashboard_token_concurrent_creation_converges(tmp_path):
    # the create-race fix: many threads racing a fresh dir must all end up with the SAME
    # token (the winner's), never a fresh one read from the briefly-empty file.
    results = []

    def grab():
        results.append(lib.dashboard_token(tmp_path))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1  # no divergent tokens
    assert (tmp_path / ".dashboard-token").read_text(encoding="utf-8").strip() == results[0]


def test_dashboard_port_and_url(tmp_path, monkeypatch):
    monkeypatch.delenv("SMBOS_DASHBOARD_PORT", raising=False)
    assert lib.dashboard_port(tmp_path) == 8765  # default
    (tmp_path / "triggers.json").write_text('{"dashboard_port": 9001}', encoding="utf-8")
    assert lib.dashboard_port(tmp_path) == 9001  # configured
    monkeypatch.setenv("SMBOS_DASHBOARD_PORT", "9100")
    assert lib.dashboard_port(tmp_path) == 9100  # env wins
    url = lib.dashboard_url(tmp_path)
    assert url == "http://127.0.0.1:9100/?t={}".format(lib.dashboard_token(tmp_path))


def test_terminal_notifier_falls_back_to_brew_paths(monkeypatch):
    # Under a minimal PATH (run_sop background runs, launchd digest), shutil.which misses a brew
    # install; the known-path fallback must still find it so the click target works.
    monkeypatch.setattr(lib.shutil, "which", lambda name: None)
    monkeypatch.setattr(lib.os.path, "exists",
                        lambda p: p == "/opt/homebrew/bin/terminal-notifier")
    assert lib._terminal_notifier() == "/opt/homebrew/bin/terminal-notifier"
    monkeypatch.setattr(lib.os.path, "exists", lambda p: False)
    assert lib._terminal_notifier() is None


def test_dashboard_url_returns_none_on_token_failure(tmp_path, monkeypatch):
    # notify() is called on error paths; a token-dir hiccup must yield None, not raise.
    def boom(_):
        raise PermissionError("sop dir unwritable")
    monkeypatch.setattr(lib, "dashboard_token", boom)
    assert lib.dashboard_url(tmp_path) is None


def test_iter_sops_skips_runtime_dirs(library):
    for d in ["pending", "queue", "work", "payloads", "archive"]:
        sub = library / d
        sub.mkdir(exist_ok=True)
        (sub / "x.md").write_text("---\nid: not-a-sop\n---\n", encoding="utf-8")
    ids = [p.stem for p in lib.iter_sops(library)]
    assert ids == ["weekly-metrics-report"]
    with_archive = [p.stem for p in lib.iter_sops(library, include_archive=True)]
    assert "x" in with_archive and "weekly-metrics-report" in with_archive


def test_frontmatter_parsing(library):
    p = next(lib.iter_sops(library))
    meta = lib.parse_frontmatter(p.read_text(encoding="utf-8"))
    assert meta["id"] == "weekly-metrics-report"
    assert meta["status"] == "active"
    meta2, body = lib.split_frontmatter(p.read_text(encoding="utf-8"))
    assert meta2["id"] == meta["id"]
    assert body.startswith("\n# Weekly metrics report")
    assert lib.frontmatter_field(p, "status") == "active"
    assert lib.frontmatter_field(p, "nope") is None


def test_find_sop_by_stem_and_id(library):
    make_sop(library, id="send-invoice", title="Send an invoice", category="finance")
    assert lib.find_sop(library, "send-invoice").stem == "send-invoice"
    assert lib.find_sop(library, "missing") is None


def test_runs_and_month_spend(library):
    from datetime import date
    prefix = date.today().strftime("%Y-%m")
    lib.append_run(library, {"ts": f"{prefix}-01T00:00:00+00:00", "cost_usd": 0.4})
    lib.append_run(library, {"ts": "2001-01-01T00:00:00+00:00", "cost_usd": 5.0})
    (library / "runs.jsonl").open("a").write("not json\n")
    assert len(lib.read_runs(library)) == 2
    assert abs(lib.month_spend(library) - 0.4) < 1e-9


def test_resolve_sop_dir_env(tmp_path, monkeypatch):
    d = tmp_path / "elsewhere"
    d.mkdir()
    monkeypatch.setenv("SOP_DIR", str(d))
    assert lib.resolve_sop_dir() == d
    monkeypatch.delenv("SOP_DIR")
    assert lib.resolve_sop_dir(explicit=str(d)) == d


def test_digest_not_treated_as_sop(tmp_path):
    from smbos_lib import iter_sops, find_sop
    d = tmp_path / "sops"
    (d / "ops").mkdir(parents=True)
    (d / "DIGEST.md").write_text("# Your day\n3 waiting.\n")  # generated, no frontmatter
    (d / "ops" / "real.md").write_text("---\nid: real\ntitle: Real\n---\n# Real\n")
    names = [p.name for p in iter_sops(d)]
    assert "DIGEST.md" not in names and "real.md" in names
    assert find_sop(d, "DIGEST") is None


def test_run_marker_running_then_clear(library):
    # a real running run holds the SOP lock; the marker without the lock reads as stopped
    lock = lib.acquire_run_lock(library, "weekly-metrics-report")
    try:
        m = lib.mark_run_active(library, "weekly-metrics-report", "prepare", "dashboard")
        runs = lib.active_runs(library)
        assert len(runs) == 1
        assert runs[0]["sop"] == "weekly-metrics-report"
        assert runs[0]["mode"] == "prepare"
        assert runs[0]["state"] == "running"  # lock held = a live run
        lib.clear_run_active(m)
        assert lib.active_runs(library) == []
    finally:
        lib.release_run_lock(lock)


def test_run_marker_stalled_when_lock_free(library):
    # marker present but no run holds the lock (crashed/killed): stopped, not running.
    # A zombie or reused pid would fool os.kill(0); the released flock does not.
    import json
    from datetime import datetime, timezone
    d = library / "active-runs"
    d.mkdir(exist_ok=True)
    (d / "x__2147483646.json").write_text(json.dumps(
        {"sop": "x", "pid": 2147483646,
         "started": datetime.now(timezone.utc).isoformat(),
         "mode": "prepare", "source": "dashboard"}), encoding="utf-8")
    runs = lib.active_runs(library)
    assert len(runs) == 1 and runs[0]["state"] == "stalled"


def test_run_marker_stalled_when_too_old(library):
    import json, os
    from datetime import datetime, timezone, timedelta
    # age backstop: even with the lock held, a run older than the cutoff is stalled
    lock = lib.acquire_run_lock(library, "y")
    try:
        d = library / "active-runs"
        d.mkdir(exist_ok=True)
        old = (datetime.now(timezone.utc) - timedelta(seconds=3000)).isoformat()
        (d / f"y__{os.getpid()}.json").write_text(json.dumps(
            {"sop": "y", "pid": os.getpid(), "started": old}), encoding="utf-8")
        assert lib.active_runs(library)[0]["state"] == "stalled"
    finally:
        lib.release_run_lock(lock)


def test_mark_run_supersedes_same_sop(library):
    import json, os
    d = library / "active-runs"
    d.mkdir(exist_ok=True)
    (d / "dup__111.json").write_text(json.dumps({"sop": "dup", "pid": 111, "started": "x"}), encoding="utf-8")
    lib.mark_run_active(library, "dup")  # prunes prior dup__*.json, writes one for this pid
    files = list(d.glob("dup__*.json"))
    assert len(files) == 1 and str(os.getpid()) in files[0].name


# --- relocated run-gate + parked-result helpers (cutover: moved from serve_dashboard) ---

def test_required_inputs_reads_frontmatter(tmp_path):
    d = tmp_path / "sops"
    (d / "ops").mkdir(parents=True)
    (d / "ops" / "with-inputs.md").write_text(
        "---\nid: with-inputs\nrun_inputs: invoice number, client\n---\nbody", encoding="utf-8")
    (d / "ops" / "no-inputs.md").write_text("---\nid: no-inputs\n---\nbody", encoding="utf-8")
    assert lib.required_inputs(d, "with-inputs") == "invoice number, client"
    assert lib.required_inputs(d, "no-inputs") is None
    assert lib.required_inputs(d, "missing") is None


def test_has_unrecorded_changes_drift(tmp_path):
    d = tmp_path / "sops"
    (d / "ops").mkdir(parents=True)
    # unstamped (no content_hash) is NOT drift; a wrong stamped hash IS drift
    (d / "ops" / "fresh.md").write_text("---\nid: fresh\nstatus: draft\n---\nbody", encoding="utf-8")
    (d / "ops" / "stale.md").write_text(
        "---\nid: stale\ncontent_hash: deadbeef\n---\nbody changed since stamp", encoding="utf-8")
    assert lib.has_unrecorded_changes(d, "fresh") is False
    assert lib.has_unrecorded_changes(d, "stale") is True
    assert lib.has_unrecorded_changes(d, "missing") is False


def test_resolve_pending_file_approve_discard_and_errors(tmp_path):
    import pytest
    pend = tmp_path / "pending"
    pend.mkdir()
    (pend / "p1.md").write_text("---\nstatus: pending\n---\nresult", encoding="utf-8")
    assert lib.resolve_pending_file(tmp_path, "p1.md", "approve") == "approved"
    body = (pend / "p1.md").read_text(encoding="utf-8")
    assert "status: approved" in body and "approved via dashboard" in body
    (pend / "p2.md").write_text("---\nstatus: pending\n---\nresult", encoding="utf-8")
    assert lib.resolve_pending_file(tmp_path, "p2.md", "discard") == "discarded"
    # only the basename is used: a traversal name reduces to <basename> inside pending/, so one
    # whose basename is absent raises rather than escaping to a real outside file (proves the guard)
    with pytest.raises(FileNotFoundError):
        lib.resolve_pending_file(tmp_path, "../../etc/hosts", "approve")
    with pytest.raises(ValueError):
        lib.resolve_pending_file(tmp_path, "p2.md", "bogus")
    with pytest.raises(FileNotFoundError):
        lib.resolve_pending_file(tmp_path, "gone.md", "approve")


# --- relocated stateful helpers (cutover PR2: queue_run/append_suggestion/sop_declared_folder) ---

def _sop(d, sid, extra=""):
    (d / "ops").mkdir(parents=True, exist_ok=True)
    (d / "ops" / f"{sid}.md").write_text(f"---\nid: {sid}\n{extra}---\nbody\n", encoding="utf-8")


def test_is_interactive_only(tmp_path):
    d = tmp_path / "sops"
    _sop(d, "live", "interactive_only: true\n")
    _sop(d, "yesish", "interactive_only: YES\n")
    _sop(d, "headless", "interactive_only: false\n")
    _sop(d, "plain")
    assert lib.is_interactive_only(d, "live") is True
    assert lib.is_interactive_only(d, "yesish") is True   # case-insensitive
    assert lib.is_interactive_only(d, "headless") is False
    assert lib.is_interactive_only(d, "plain") is False
    assert lib.is_interactive_only(d, "missing") is False


def test_sop_declared_folder(tmp_path):
    d = tmp_path / "sops"
    proj = tmp_path / "project"; proj.mkdir()
    _sop(d, "client", f"folder: {proj}\n")
    _sop(d, "ghost", f"folder: {tmp_path}/nope\n")  # declared dir doesn't exist
    _sop(d, "nofolder")
    assert lib.sop_declared_folder(d, "client") == str(proj.resolve())
    assert lib.sop_declared_folder(d, "ghost") is None      # nonexistent dir -> None
    assert lib.sop_declared_folder(d, "nofolder") is None
    assert lib.sop_declared_folder(d, "missing") is None


def test_queue_run_folder_logic(tmp_path):
    import pytest
    d = tmp_path / "sops"
    _sop(d, "report")
    proj = tmp_path / "proj"; proj.mkdir()
    _sop(d, "client", f"folder: {proj}\n")
    # scope here + a real launch_cwd -> that folder; anywhere -> none; home/sop_dir -> none
    assert lib.queue_run(d, "report", scope="here", launch_cwd="/some/projA")[1] == "/some/projA"
    assert lib.queue_run(d, "report", scope="anywhere", launch_cwd="/some/projA")[1] == ""
    assert lib.queue_run(d, "report", scope="here", launch_cwd=str(d))[1] == ""
    assert lib.queue_run(d, "report", scope="here", launch_cwd=None)[1] == ""
    # a declared folder overrides launch_cwd
    assert lib.queue_run(d, "client", scope="here", launch_cwd="/some/projA")[1] == str(proj.resolve())
    # writes a queue file; unknown sop raises
    assert any((d / "queue").glob("*.md"))
    with pytest.raises(ValueError):
        lib.queue_run(d, "no-such-sop")


def test_append_suggestion(tmp_path):
    import pytest
    d = tmp_path / "sops"
    (d / "ops").mkdir(parents=True)
    sop = d / "ops" / "proc.md"
    sop.write_text("---\nid: proc\n---\nbody\n\n## Changelog\n- v1\n", encoding="utf-8")
    lib.append_suggestion(d, "ops/proc.md", "tighten the close step")
    text = sop.read_text(encoding="utf-8")
    assert lib.NOTES_HEADING in text and "tighten the close step" in text
    # the note lands before the Changelog
    assert text.index(lib.NOTES_HEADING) < text.index("## Changelog")
    # a path escaping the SOP dir is refused; a non-SOP target is refused
    with pytest.raises(PermissionError):
        lib.append_suggestion(d, "../../etc/hosts", "x")
    (d / "INDEX.md").write_text("# idx\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        lib.append_suggestion(d, "INDEX.md", "x")


def test_run_sop_command_builder(tmp_path):
    # the shared builder both the daemon and the app use to invoke run_sop (parity gate)
    cmd = lib.run_sop_command(tmp_path, "weekly-report", inputs="sources: Stripe")
    assert cmd[1].endswith("run_sop.py")
    assert cmd[2] == "weekly-report"
    assert cmd[cmd.index("--source") + 1] == "dashboard"
    assert cmd[cmd.index("--sop-dir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--inputs") + 1] == "sources: Stripe"
    bare = lib.run_sop_command(tmp_path, "x")
    assert "--inputs" not in bare and "--prepare" not in bare
    assert "--prepare" in lib.run_sop_command(tmp_path, "x", prepare=True)
    assert lib.run_sop_command(tmp_path, "x", source="cron")[4] == "cron"
