import io
import json

import engine_action
import run_gate
import state_store as ss


def test_engine_resolve_dequeue_taskstatus_refusals(tmp_path):
    (tmp_path / "queue").mkdir()
    assert engine_action.main(["resolve", str(tmp_path), "--file=nope.md", "--decision=approve"]) == 4  # 404
    assert engine_action.main(["dequeue", str(tmp_path), "--file=nope.md"]) == 4                          # 404
    assert engine_action.main(["task-status", str(tmp_path), "--task-id=1", "--status=bogus"]) == 8       # 400


def test_engine_dequeue_basename_only_no_traversal(tmp_path):
    (tmp_path / "queue").mkdir()
    # a traversal attempt is reduced to its basename -> not found, never escapes queue/
    assert engine_action.main(["dequeue", str(tmp_path), "--file=../../secret.md"]) == 4


def test_engine_dequeue_removes_a_queued_file(tmp_path, capsys):
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "q.md").write_text("---\nsop: x\nstatus: queued\n---\n", encoding="utf-8")
    assert engine_action.main(["dequeue", str(tmp_path), "--file=q.md"]) == 0
    assert not (tmp_path / "queue" / "q.md").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "dequeued"


def test_engine_task_status_recovers_in_flight(tmp_path, capsys):
    ss.upsert_task(str(tmp_path), "ops", "x", "task", status="in_flight")
    tid = ss.in_flight(str(tmp_path))[0]["id"]
    assert engine_action.main(["task-status", str(tmp_path), "--task-id=" + str(tid), "--status=waiting"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "waiting", "task_id": tid}
    assert ss.in_flight(str(tmp_path)) == []  # left in_flight -> now waiting (back on the plate)
    # a second click (now not in flight) is the CAS conflict -> 9 (409)
    assert engine_action.main(["task-status", str(tmp_path), "--task-id=" + str(tid), "--status=done"]) == 9


def test_engine_run_refuses_draft(tmp_path, capsys):
    # a draft full run is refused by the gate -> exit 3 (the broker maps this to 409) + an owner message
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "d.md").write_text("---\nid: d\ntitle: D\nstatus: draft\n---\n# D\n", encoding="utf-8")
    code = engine_action.main(["run", str(tmp_path), "d"])
    assert code == 3
    assert "draft" in json.loads(capsys.readouterr().out)["detail"]


def test_engine_run_spawns_active(tmp_path, capsys, monkeypatch):
    # an active SOP passes the gate and the engine spawns the runner (stubbed) -> exit 0 + the 200 body
    spawned = []
    monkeypatch.setattr(run_gate, "spawn_run", lambda *a, **k: spawned.append((a, k)))
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "a.md").write_text("---\nid: a\ntitle: A\nstatus: active\n---\n# A\n", encoding="utf-8")
    code = engine_action.main(["run", str(tmp_path), "a"])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"status": "started", "sop": "a"}
    assert len(spawned) == 1


def test_engine_run_inputs_with_leading_dash_is_a_value_not_a_flag(tmp_path, capsys, monkeypatch):
    # the broker passes --inputs=<value>; an inputs value beginning with '-' must reach spawn as the
    # value, NOT be misparsed by argparse as an option (which would 500 the run).
    captured = {}
    monkeypatch.setattr(run_gate, "spawn_run",
                        lambda sop_dir, sid, inputs=None, prepare=False: captured.update(inputs=inputs, prepare=prepare))
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "a.md").write_text("---\nid: a\ntitle: A\nstatus: active\n---\n# A\n", encoding="utf-8")
    code = engine_action.main(["run", str(tmp_path), "a", "--inputs=--prepare"])
    assert code == 0
    assert captured["inputs"] == "--prepare"   # passed through as the value
    assert captured["prepare"] is False        # NOT consumed as the --prepare flag


def test_engine_run_inputs_from_stdin(tmp_path, capsys, monkeypatch):
    # the broker passes inputs on STDIN (--inputs-stdin): unbounded + no argparse misparse of a
    # dash-leading value. They must reach spawn verbatim (stripped).
    captured = {}
    monkeypatch.setattr(run_gate, "spawn_run",
                        lambda sop_dir, sid, inputs=None, prepare=False: captured.update(inputs=inputs))
    monkeypatch.setattr("sys.stdin", io.StringIO("  --leading-dash and spaces  "))
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "a.md").write_text("---\nid: a\ntitle: A\nstatus: active\n---\n# A\n", encoding="utf-8")
    code = engine_action.main(["run", str(tmp_path), "a", "--inputs-stdin"])
    assert code == 0
    assert captured["inputs"] == "--leading-dash and spaces"  # stripped, passed through, not a flag


def test_engine_autonomy_gate_and_write(tmp_path):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "act.md").write_text("---\nid: act\ntitle: A\nstatus: active\n---\n# A\n", encoding="utf-8")
    (tmp_path / "ops" / "wip.md").write_text("---\nid: wip\ntitle: W\nstatus: draft\n---\n# W\n", encoding="utf-8")
    assert engine_action.main(["autonomy", str(tmp_path), "act", "--level=bogus"]) == 8       # 400 bad level
    assert engine_action.main(["autonomy", str(tmp_path), "nope", "--level=with_me"]) == 4     # 404 unknown
    assert engine_action.main(["autonomy", str(tmp_path), "wip", "--level=on_its_own"]) == 9   # 409 draft
    assert engine_action.main(["autonomy", str(tmp_path), "act", "--level=with_me"]) == 0
    import smbos_lib as lib
    assert lib.autonomy_level(str(tmp_path), "act") == "with_me"  # persisted to frontmatter


def test_engine_autonomy_refuses_drift_and_restamps(tmp_path):
    # the trust property THROUGH the engine path (stdlib test job): a clean write re-stamps; a body
    # that drifted out-of-band makes the next write refuse (SopDrifted -> exit 9 -> 409), not bless it.
    import smbos_lib as lib
    (tmp_path / "ops").mkdir()
    p = tmp_path / "ops" / "act.md"
    p.write_text("---\nid: act\ntitle: A\nstatus: active\n---\n# A\nbody\n", encoding="utf-8")
    meta, body = lib.split_frontmatter(p.read_text(encoding="utf-8"))
    p.write_text(lib.set_frontmatter_fields(p.read_text(encoding="utf-8"),
                 {"content_hash": lib.content_fingerprint(body, meta)}), encoding="utf-8")  # stamp it
    assert lib.has_unrecorded_changes(str(tmp_path), "act") is False
    assert engine_action.main(["autonomy", str(tmp_path), "act", "--level=prepare_ask"]) == 0
    assert lib.has_unrecorded_changes(str(tmp_path), "act") is False  # re-stamped, not drift
    p.write_text(p.read_text(encoding="utf-8") + "\nout-of-band edit\n", encoding="utf-8")
    assert engine_action.main(["autonomy", str(tmp_path), "act", "--level=on_its_own"]) == 9  # drift -> 409


def test_engine_queue(tmp_path):
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "act.md").write_text("---\nid: act\ntitle: A\nstatus: active\n---\n# A\n", encoding="utf-8")
    assert engine_action.main(["queue", str(tmp_path), "nope"]) == 8  # unknown task -> 400
    assert engine_action.main(["queue", str(tmp_path), "act"]) == 0
    assert any((tmp_path / "queue").glob("*.md"))  # a queue file was written


def test_engine_run_internal_error_is_caught(tmp_path, capsys, monkeypatch):
    # an unexpected failure in the engine -> exit 1 (the broker maps this to 500), never an unhandled crash
    def boom(*a, **k):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(run_gate, "gate_run", boom)
    code = engine_action.main(["run", str(tmp_path), "a"])
    assert code == 1
    assert "detail" in json.loads(capsys.readouterr().out)
