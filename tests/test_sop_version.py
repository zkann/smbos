import sys

import pytest

import sop_version as sv
from conftest import make_sop
from smbos_lib import (content_fingerprint, is_drifted, parse_frontmatter,
                       set_frontmatter_fields, split_frontmatter)


# ---------- lib: fingerprint ----------

def test_fingerprint_ignores_journal_sections_and_line_endings():
    base = "## Steps\n1. Do it.\n\n## Notes for next revision\n\n## Changelog\n- v1: created.\n"
    noted = base.replace("## Notes for next revision\n",
                         "## Notes for next revision\n- (via dashboard) lead with cash\n")
    logged = base.replace("- v1: created.", "- v1: created.\n- v2 (2026-06-10): tweaked.")
    crlf = base.replace("\n", "\r\n")
    assert content_fingerprint(base) == content_fingerprint(noted)
    assert content_fingerprint(base) == content_fingerprint(logged)
    assert content_fingerprint(base) == content_fingerprint(crlf)
    assert content_fingerprint(base) != content_fingerprint(base.replace("Do it.", "Do it twice."))


def test_drift_semantics():
    body = "## Steps\n1. Do it.\n"
    assert not is_drifted({}, body)  # unstamped is not drift
    assert not is_drifted({"content_hash": content_fingerprint(body)}, body)
    assert is_drifted({"content_hash": "deadbeef0000"}, body)


def test_set_frontmatter_fields_upserts_in_place():
    doc = "---\nid: x\nversion: 1\nstatus: trusted\n---\n\n# X\nbody\n"
    out = set_frontmatter_fields(doc, {"version": 2, "content_hash": "abc"})
    meta, body = split_frontmatter(out)
    assert meta["version"] == "2" and meta["content_hash"] == "abc"
    assert meta["status"] == "trusted"
    assert body.endswith("body\n")
    assert out.index("id: x") < out.index("version: 2") < out.index("status: trusted")
    with pytest.raises(ValueError):
        set_frontmatter_fields("no frontmatter here", {"a": 1})


# ---------- CLI: stamp / check / bump ----------

def run_cli(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["sop_version.py", *argv])
    sv.main()
    return capsys.readouterr().out


def test_stamp_then_check_silent(library, monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "stamp", "--all")
    assert "1 procedure" in out
    meta = parse_frontmatter((library / "ops" / "weekly-metrics-report.md").read_text())
    assert len(meta["content_hash"]) == 12
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "check")
    assert out == ""


def test_check_reports_drift_and_trusted_warning(library, monkeypatch, capsys):
    p = make_sop(library, id="t1", title="Trusted one", status="trusted")
    run_cli(monkeypatch, capsys, "--sop-dir", str(library), "stamp", "t1")
    p.write_text(p.read_text().replace("Do the thing.", "Do the OTHER thing."))
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "check")
    assert "t1: changed since v1 was recorded" in out
    assert "will not run unattended" in out
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "check", "--json")
    import json
    items = json.loads(out)
    assert items[0]["id"] == "t1" and items[0]["status"] == "trusted"


def test_notes_append_does_not_drift(library, monkeypatch, capsys):
    p = library / "ops" / "weekly-metrics-report.md"
    run_cli(monkeypatch, capsys, "--sop-dir", str(library), "stamp", "weekly-metrics-report")
    p.write_text(p.read_text().replace(
        "## Notes for next revision\n", "## Notes for next revision\n- (via dashboard) hi\n"))
    assert run_cli(monkeypatch, capsys, "--sop-dir", str(library), "check") == ""


def test_bump_full_bookkeeping(library, monkeypatch, capsys):
    p = make_sop(library, id="t2", title="Trusted two", status="trusted")
    text = p.read_text().replace("clean_runs: 0", "clean_runs: 4")
    p.write_text(text.replace("Do the thing.", "Edited step."))
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "bump", "t2",
                  "--note", "switched to net-15 terms")
    assert "v2" in out and "back to active" in out
    meta, body = split_frontmatter(p.read_text())
    assert meta["version"] == "2"
    assert meta["status"] == "active"
    assert meta["clean_runs"] == "0"
    assert not is_drifted(meta, body)
    assert "- v2 (" in body and "switched to net-15 terms" in body
    # changelog line landed inside the Changelog section, after v1
    assert body.index("- v1 (2026-06-01): created.") < body.index("switched to net-15 terms")


def test_bump_creates_changelog_when_missing(library, monkeypatch, capsys):
    p = make_sop(library, id="t3", title="No log")
    p.write_text(p.read_text().split("## Changelog")[0])
    run_cli(monkeypatch, capsys, "--sop-dir", str(library), "bump", "t3", "--note", "first edit")
    body = split_frontmatter(p.read_text())[1]
    assert "## Changelog" in body and "first edit" in body


def test_bump_missing_sop_exits(library, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv",
                        ["sop_version.py", "--sop-dir", str(library), "bump", "nope", "--note", "x"])
    with pytest.raises(SystemExit):
        sv.main()


def test_capability_fields_are_fingerprinted():
    """Editing research_domains on a stamped SOP must read as drift: the stamp
    is what makes the allowlist owner-sanctioned (dogfooding find 2026-06-12)."""
    body = "## Steps\n1. Do it.\n"
    meta = {"research_domains": "example.com", "deliverable": "a list"}
    h = content_fingerprint(body, meta)
    assert not is_drifted({**meta, "content_hash": h}, body)
    widened = {**meta, "research_domains": "example.com, attacker.example", "content_hash": h}
    assert is_drifted(widened, body)
    re_read = {**meta, "research_reads": "~/.ssh/id_rsa", "content_hash": h}
    assert is_drifted(re_read, body)


def test_interactive_only_is_fingerprinted_but_backward_compatible():
    """interactive_only gates the unattended runner, so stripping it out-of-band
    must read as drift. But folding it in must NOT re-fingerprint the SOPs that
    do not carry the flag (no mass false-drift on upgrade)."""
    body = "## Steps\n1. Do it.\n"
    # backward compatible: an absent/empty flag leaves the hash unchanged
    assert content_fingerprint(body, {}) == content_fingerprint(body)
    assert content_fingerprint(body, {"deliverable": "x"}) == \
        content_fingerprint(body, {"deliverable": "x", "interactive_only": ""})
    # stamped WITH the flag; removing it out-of-band trips drift
    meta = {"interactive_only": "true"}
    h = content_fingerprint(body, meta)
    assert not is_drifted({**meta, "content_hash": h}, body)   # flag present -> clean
    assert is_drifted({"content_hash": h}, body)               # flag stripped -> drift
    # truthy variants normalize to the same fingerprint
    assert content_fingerprint(body, {"interactive_only": "yes"}) == h


def test_stamp_all_skips_frontmatterless_files(library, monkeypatch, capsys):
    # a non-SOP markdown file iter_sops DOES yield (unlike SKIP_NAMES entries)
    (library / "ops" / "scratch-notes.md").write_text("# notes\nno frontmatter\n")
    out = run_cli(monkeypatch, capsys, "--sop-dir", str(library), "stamp", "--all")
    assert "procedure" in out  # did not crash on the frontmatterless file
    assert "content_hash" not in (library / "ops" / "scratch-notes.md").read_text()
    # single-file stamp of a non-SOP exits cleanly, not a traceback
    import sys as _sys, pytest as _pt
    monkeypatch.setattr(_sys, "argv",
                        ["sop_version.py", "--sop-dir", str(library), "stamp", "scratch-notes"])
    with _pt.raises(SystemExit):
        sv.main()
