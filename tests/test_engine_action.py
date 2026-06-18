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


def test_engine_run_internal_error_is_caught(tmp_path, capsys, monkeypatch):
    # an unexpected failure in the engine -> exit 1 (the broker maps this to 500), never an unhandled crash
    def boom(*a, **k):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(run_gate, "gate_run", boom)
    code = engine_action.main(["run", str(tmp_path), "a"])
    assert code == 1
    assert "detail" in json.loads(capsys.readouterr().out)
