import pytest

import serve_dashboard as sv
from conftest import make_sop


def test_resolve_pending_file(library):
    pend = library / "pending"
    pend.mkdir()
    (pend / "a.md").write_text("---\nsop: x\nstatus: pending\n---\nbody\n")
    assert sv.resolve_pending_file(library, "a.md", "approve") == "approved"
    assert "status: approved" in (pend / "a.md").read_text()
    (pend / "b.md").write_text("---\nsop: x\nstatus: pending\n---\n")
    assert sv.resolve_pending_file(library, "b.md", "discard") == "discarded"
    with pytest.raises(FileNotFoundError):
        sv.resolve_pending_file(library, "../../etc/hosts", "approve")
    with pytest.raises(ValueError):
        sv.resolve_pending_file(library, "a.md", "explode")


def test_queue_scopes(library, monkeypatch):
    monkeypatch.setattr(sv, "LAUNCH_CWD", "/somewhere/projectA")
    sv.queue_run(library, "weekly-metrics-report", scope="here")
    f = sorted((library / "queue").glob("*.md"))[-1].read_text()
    assert "project: /somewhere/projectA" in f
    sv.queue_run(library, "weekly-metrics-report", scope="anywhere")
    f2 = sorted((library / "queue").glob("*.md"))[-1].read_text()
    assert "project: \n" in f2
    with pytest.raises(ValueError):
        sv.queue_run(library, "no-such-sop")


def test_queue_from_home_is_unscoped(library, monkeypatch):
    import pathlib
    monkeypatch.setattr(sv, "LAUNCH_CWD", str(pathlib.Path.home()))
    sv.queue_run(library, "weekly-metrics-report", scope="here")
    f = sorted((library / "queue").glob("*.md"))[-1].read_text()
    assert "project: \n" in f


def test_required_inputs_gate(library, monkeypatch):
    make_sop(library, id="needs-stuff", status="active",
             extra="run_inputs: which client\n")
    monkeypatch.setattr(sv, "LAUNCH_CWD", "/somewhere")
    with pytest.raises(ValueError, match="which client"):
        sv.start_run(library, "needs-stuff")


def test_append_suggestion_placement(library):
    p = library / "ops" / "weekly-metrics-report.md"
    sv.append_suggestion(library, "ops/weekly-metrics-report.md", "Lead with cash")
    text = p.read_text()
    notes = text.index("## Notes for next revision")
    changelog = text.index("## Changelog")
    bullet = text.index("via dashboard) Lead with cash")
    assert notes < bullet < changelog
    with pytest.raises(PermissionError):
        sv.append_suggestion(library, "../outside.md", "evil")


def test_launch_routing(library, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(sv, "open_terminal_with_claude",
                        lambda folder, prompt, terminal="terminal": calls.append((str(folder), prompt)))
    proj = tmp_path / "projA"
    proj.mkdir()
    q = library / "queue"
    q.mkdir()
    (q / "a.md").write_text(
        f"---\nsop: weekly-metrics-report\nproject: {proj}\nstatus: queued\n---\n")
    assert sv.launch(library, {"kind": "queue", "file": "a.md"}) == "launched"
    assert calls[-1][0] == str(proj)
    assert "weekly-metrics-report" in calls[-1][1]

    monkeypatch.setattr(sv, "LAUNCH_CWD", str(proj))
    assert sv.launch(library, {"kind": "sop", "id": "weekly-metrics-report"}) == "launched"
    assert calls[-1] == (str(proj), "weekly numbers")  # first trigger phrase

    assert sv.launch(library, {"kind": "approved"}) == "launched"
    assert "approved pending actions" in calls[-1][1]

    import pytest as _pt
    with _pt.raises(ValueError):
        sv.launch(library, {"kind": "queue", "file": "../../etc/hosts"})
    with _pt.raises(ValueError):
        sv.launch(library, {"kind": "explode"})


def test_launch_open_file_and_reveal(library, monkeypatch):
    runs = []
    monkeypatch.setattr(sv.subprocess, "run",
                        lambda cmd, **kw: runs.append(cmd))
    assert sv.launch(library, {"kind": "open_file", "id": "weekly-metrics-report"}) == "opened file"
    assert runs[-1][0] == "open" and runs[-1][1].endswith("weekly-metrics-report.md")
    assert sv.launch(library, {"kind": "reveal"}) == "opened folder"
    assert runs[-1] == ["open", str(library)]


def test_applescript_escape():
    assert sv.applescript_escape('say "hi" \\ there') == 'say \\"hi\\" \\\\ there'


def test_preferred_terminal(library, monkeypatch):
    import json
    monkeypatch.setattr(sv, "TERM_PROGRAM", "Apple_Terminal")
    assert sv.preferred_terminal(library) == "terminal"
    monkeypatch.setattr(sv, "TERM_PROGRAM", "iTerm.app")
    assert sv.preferred_terminal(library) == "iterm"
    (library / "triggers.json").write_text(json.dumps({"terminal": "terminal"}))
    assert sv.preferred_terminal(library) == "terminal"  # config beats detection


def test_iterm_script_used(library, monkeypatch):
    scripts = []
    monkeypatch.setattr(sv.subprocess, "run",
                        lambda cmd, **kw: scripts.append(cmd[2]))
    monkeypatch.setattr(sv.sys, "platform", "darwin")
    sv.open_terminal_with_claude(library, "weekly numbers", terminal="iterm")
    assert 'tell application "iTerm"' in scripts[-1]
    assert "write text" in scripts[-1] and "weekly numbers" in scripts[-1]
    sv.open_terminal_with_claude(library, "x", terminal="terminal")
    assert 'tell application "Terminal"' in scripts[-1]


def test_start_run_refuses_unrecorded_changes(library, monkeypatch):
    from smbos_lib import content_fingerprint, set_frontmatter_fields, split_frontmatter
    sop = library / "ops" / "weekly-metrics-report.md"
    text = sop.read_text()
    _m, body = split_frontmatter(text)
    sop.write_text(set_frontmatter_fields(text, {"content_hash": content_fingerprint(body, _m)}))
    sop.write_text(sop.read_text().replace("Do the thing.", "Do something else."))
    with pytest.raises(ValueError, match="outside the normal save flow"):
        sv.start_run(library, "weekly-metrics-report")


def test_api_prepare_mode_and_lock(library, monkeypatch):
    calls = []
    class FakePopen:
        def __init__(self, cmd, **kw): calls.append(cmd)
    monkeypatch.setattr(sv.subprocess, "Popen", FakePopen)
    sv.start_run(library, "weekly-metrics-report", prepare=True)
    assert "--prepare" in calls[-1]
    from smbos_lib import acquire_run_lock, release_run_lock
    handle = acquire_run_lock(library, "weekly-metrics-report")
    with pytest.raises(ValueError, match="already running"):
        sv.start_run(library, "weekly-metrics-report", prepare=True)
    release_run_lock(handle)
    # a leftover lockfile without a live flock does not block the dashboard
    sv.start_run(library, "weekly-metrics-report", prepare=True)


def test_discard_reason_lands_in_notes(library):
    pend = library / "pending"; pend.mkdir()
    (pend / "a.md").write_text("---\nsop: weekly-metrics-report\nstatus: pending\n---\nbody\n")
    sv.resolve_pending_file(library, "a.md", "discard")
    # the endpoint-level reason path: emulate what do_POST does
    from smbos_lib import find_sop as lf, frontmatter_field as ff
    sop_id = ff(pend / "a.md", "sop")
    target = lf(library, sop_id)
    sv.append_suggestion(library, str(target.relative_to(library)),
                         "(discarded a prepared result) too generic")
    text = target.read_text()
    assert "via dashboard) (discarded a prepared result) too generic" in text
