import subprocess
from pathlib import Path

from conftest import REPO

HOOK = REPO / "hooks" / "session-start.sh"


def run_hook(library, cwd):
    import os
    env = dict(os.environ)
    env["SOP_DIR"] = str(library)
    return subprocess.run(["bash", str(HOOK)], capture_output=True, text=True,
                          env=env, cwd=str(cwd), timeout=30).stdout


def test_protocol_and_plain_words(library, tmp_path):
    out = run_hook(library, tmp_path)
    assert "PLAIN WORDS" in out
    assert "MATCH." in out and "COMPOSE." in out
    assert "BOOTSTRAP MODE" in out  # one active SOP < 5


def test_parked_and_approved_detection(library, tmp_path):
    pend = library / "pending"
    pend.mkdir()
    (pend / "a.md").write_text("---\nsop: x\nstatus: pending\n---\n")
    (pend / "b.md").write_text("---\nsop: y\nstatus: approved\n---\n")
    out = run_hook(library, tmp_path)
    assert "WAITING FOR YOU (parked approvals): 1" in out
    assert "APPROVED ACTIONS TO EXECUTE: 1" in out


def test_queue_routing_by_cwd(library, tmp_path):
    proj_a = tmp_path / "projectA"
    proj_b = tmp_path / "projectB"
    proj_a.mkdir()
    proj_b.mkdir()
    q = library / "queue"
    q.mkdir()
    (q / "a.md").write_text(f"---\nsop: s\nproject: {proj_a}\nstatus: queued\n---\n")
    (q / "anywhere.md").write_text("---\nsop: s\nproject: \nstatus: queued\n---\n")
    in_a = run_hook(library, proj_a)
    assert "ON YOUR PLATE (this session): 2" in in_a
    assert "ON YOUR PLATE ELSEWHERE" not in in_a
    in_b = run_hook(library, proj_b)
    assert "ON YOUR PLATE (this session): 1" in in_b
    assert "ON YOUR PLATE ELSEWHERE" in in_b and "projectA" in in_b


def test_work_items_routed(library, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    w = library / "work"
    w.mkdir()
    (w / "a.md").write_text("---\nid: a\ntitle: Anywhere item\nstage: build\nstatus: active\nproject: \n---\n")
    (w / "b.md").write_text(f"---\nid: b\ntitle: Proj item\nstage: plan\nstatus: blocked\nproject: {proj}\n---\n")
    out_elsewhere = run_hook(library, tmp_path)
    assert "Anywhere item: at stage 'build'" in out_elsewhere
    assert "Proj item" not in out_elsewhere
    out_proj = run_hook(library, proj)
    assert "Proj item: at stage 'plan' (BLOCKED)" in out_proj


def test_hook_bash_syntax():
    r = subprocess.run(["bash", "-n", str(HOOK)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_unrecorded_changes_section(library, tmp_path):
    from smbos_lib import content_fingerprint, set_frontmatter_fields, split_frontmatter
    out = run_hook(library, tmp_path)
    assert "UNRECORDED CHANGES" not in out  # unstamped library stays quiet
    sop = library / "ops" / "weekly-metrics-report.md"
    text = sop.read_text()
    _m, body = split_frontmatter(text)
    sop.write_text(set_frontmatter_fields(text, {"content_hash": content_fingerprint(body, _m)}))
    out = run_hook(library, tmp_path)
    assert "UNRECORDED CHANGES" not in out  # stamped and clean
    sop.write_text(sop.read_text().replace("Do the thing.", "Changed."))
    out = run_hook(library, tmp_path)
    assert "UNRECORDED CHANGES" in out
    assert "weekly-metrics-report: changed since v1" in out
    assert "sop_version.py bump" in out
