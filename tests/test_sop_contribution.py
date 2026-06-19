"""Tests for sop_contribution -- the per-SOP clean-streak / library-drift metric. scripts/ is on
sys.path via conftest; SOPs are written into tmp_path so the real library is never read."""
import sop_contribution as sc


def _sop(dir_, sop_id, runs, clean, status="active"):
    (dir_ / f"{sop_id}.md").write_text(
        "---\nid: {}\ntitle: {}\nstatus: {}\nruns: {}\nclean_runs: {}\n---\n\n# {}\n".format(
            sop_id, sop_id, status, runs, clean, sop_id),
        encoding="utf-8")


def test_streak_verdicts(tmp_path):
    _sop(tmp_path, "healthy", runs=10, clean=4)   # enough runs, live streak -> ok
    _sop(tmp_path, "broken", runs=8, clean=0)     # enough runs, streak broken -> REVIEW
    _sop(tmp_path, "young", runs=2, clean=0)      # too few runs -> insufficient-evidence
    by_id = {r["id"]: r for r in sc.scan(tmp_path, floor=5)}
    assert by_id["healthy"]["verdict"] == "ok"
    assert by_id["broken"]["verdict"] == "REVIEW"
    assert by_id["young"]["verdict"] == "insufficient-evidence"


def test_mature_short_streak_is_not_flagged(tmp_path):
    # Codex's case: clean_runs is a STREAK, not a lifetime ratio, so a mature SOP with a short
    # CURRENT streak must NOT be flagged. 100 runs, streak of 3 -> ok (a clean/runs ratio would
    # have wrongly flagged 0.03).
    _sop(tmp_path, "mature", runs=100, clean=3)
    assert {r["id"]: r for r in sc.scan(tmp_path, floor=5)}["mature"]["verdict"] == "ok"


def test_missing_counter_is_no_counter(tmp_path):
    (tmp_path / "bare.md").write_text(
        "---\nid: bare\ntitle: bare\nstatus: draft\n---\n\n# bare\n", encoding="utf-8")
    assert sc.scan(tmp_path)[0]["verdict"] == "no-counter"


def test_template_index_and_noid_skipped(tmp_path):
    _sop(tmp_path, "real", runs=1, clean=1)
    (tmp_path / "_template.md").write_text("---\nid: tmpl\n---\n", encoding="utf-8")  # iter_sops skips by name
    (tmp_path / "INDEX.md").write_text("---\nid: idx\n---\n", encoding="utf-8")        # iter_sops skips by name
    (tmp_path / "notes.md").write_text("# notes, no frontmatter id\n", encoding="utf-8")  # no id -> filtered
    ids = {r["id"] for r in sc.scan(tmp_path)}
    assert ids == {"real"}


def test_archived_sops_excluded(tmp_path):
    # iter_sops excludes archive/; a retired SOP must not be flagged (Codex finding).
    _sop(tmp_path, "active-one", runs=8, clean=0)
    arch = tmp_path / "archive"
    arch.mkdir()
    _sop(arch, "retired", runs=8, clean=0)
    ids = {r["id"] for r in sc.scan(tmp_path)}
    assert ids == {"active-one"}


def test_report_lists_review_conservatively(tmp_path):
    _sop(tmp_path, "broken", runs=8, clean=0)
    out = sc.report(sc.scan(tmp_path, floor=5))
    assert "broken" in out
    assert "never auto-retire" in out  # the conservatism note is always present


def test_floor_zero_does_not_flag_unrun_sop(tmp_path):
    _sop(tmp_path, "zero-runs", runs=0, clean=0)  # degenerate --floor 0 must not flag a never-run SOP
    rec = {r["id"]: r for r in sc.scan(tmp_path, floor=0)}["zero-runs"]
    assert rec["verdict"] == "insufficient-evidence"
