from conftest import make_sop

import smbos_lib as lib


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
    m = lib.mark_run_active(library, "weekly-metrics-report", "prepare", "dashboard")
    runs = lib.active_runs(library)
    assert len(runs) == 1
    assert runs[0]["sop"] == "weekly-metrics-report"
    assert runs[0]["mode"] == "prepare"
    assert runs[0]["state"] == "running"  # this test process's pid is alive and fresh
    lib.clear_run_active(m)
    assert lib.active_runs(library) == []


def test_run_marker_stalled_when_pid_dead(library):
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
    d = library / "active-runs"
    d.mkdir(exist_ok=True)
    old = (datetime.now(timezone.utc) - timedelta(seconds=3000)).isoformat()
    (d / f"y__{os.getpid()}.json").write_text(json.dumps(
        {"sop": "y", "pid": os.getpid(), "started": old}), encoding="utf-8")
    # too old to be a legitimate live run even though the pid is alive
    assert lib.active_runs(library)[0]["state"] == "stalled"


def test_mark_run_supersedes_same_sop(library):
    import json, os
    d = library / "active-runs"
    d.mkdir(exist_ok=True)
    (d / "dup__111.json").write_text(json.dumps({"sop": "dup", "pid": 111, "started": "x"}), encoding="utf-8")
    lib.mark_run_active(library, "dup")  # prunes prior dup__*.json, writes one for this pid
    files = list(d.glob("dup__*.json"))
    assert len(files) == 1 and str(os.getpid()) in files[0].name
