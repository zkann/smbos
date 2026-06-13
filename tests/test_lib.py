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
