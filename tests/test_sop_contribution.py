"""Tests for sop_contribution -- the per-SOP contribution / library-drift metric. scripts/ is on
sys.path via conftest; SOPs are written into tmp_path so the real library is never read."""
import sop_contribution as sc


def _sop(dir_, sop_id, runs, clean, status="active"):
    (dir_ / f"{sop_id}.md").write_text(
        "---\nid: {}\ntitle: {}\nstatus: {}\nruns: {}\nclean_runs: {}\n---\n\n# {}\n".format(
            sop_id, sop_id, status, runs, clean, sop_id),
        encoding="utf-8")


def test_verdicts_by_evidence(tmp_path):
    _sop(tmp_path, "well-used", runs=10, clean=9)          # enough runs, high ratio -> ok
    _sop(tmp_path, "drifting", runs=8, clean=2)            # enough runs, low ratio -> REVIEW
    _sop(tmp_path, "young", runs=2, clean=0)               # too few runs -> insufficient-evidence
    by_id = {r["id"]: r for r in sc.scan(tmp_path, floor=5)}
    assert by_id["well-used"]["verdict"] == "ok"
    assert by_id["drifting"]["verdict"] == "REVIEW"
    assert by_id["young"]["verdict"] == "insufficient-evidence"


def test_missing_counter_is_no_counter(tmp_path):
    (tmp_path / "bare.md").write_text(
        "---\nid: bare\ntitle: bare\nstatus: draft\n---\n\n# bare\n", encoding="utf-8")
    assert sc.scan(tmp_path)[0]["verdict"] == "no-counter"


def test_index_files_skipped(tmp_path):
    _sop(tmp_path, "real", runs=1, clean=1)
    (tmp_path / "MEMORY.md").write_text("---\nid: nope\n---\n", encoding="utf-8")
    (tmp_path / "_template.md").write_text("---\nid: tmpl\n---\n", encoding="utf-8")
    ids = {r["id"] for r in sc.scan(tmp_path)}
    assert ids == {"real"}


def test_report_lists_review_conservatively(tmp_path):
    _sop(tmp_path, "drifting", runs=8, clean=2)
    out = sc.report(sc.scan(tmp_path, floor=5))
    assert "drifting" in out
    assert "never auto-retire" in out  # the conservatism note is always present
