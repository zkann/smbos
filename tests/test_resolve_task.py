"""Unit tests for resolve_task.py, the CLI a picked-up session calls to report its outcome.

Stdlib + pytest, isolated per tmp_path. The CLI resolves the library from $SOP_DIR (the launch
exports it into the session), so each test points SOP_DIR at its tmp_path. Covers the happy path
for each reportable status, the in_flight gate (a report can't disturb an already-resolved task),
and the argument validation that fails loudly."""
import pytest

import resolve_task
import state_store as ss


def _inflight(sop_dir, subject="stuck task"):
    return ss.record_task(sop_dir, "ops", "review", subject, status="in_flight")


@pytest.mark.parametrize("status,expected", [
    ("done", "done"),
    ("dismissed", "dismissed"),
    ("waiting", "waiting"),
])
def test_reports_each_outcome(tmp_path, monkeypatch, capsys, status, expected):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    tid = _inflight(tmp_path)
    assert resolve_task.main([str(tid), status]) == 0
    assert ss.get_task(tmp_path, tid)["status"] == expected
    assert str(tid) in capsys.readouterr().out


def test_late_report_does_not_disturb_a_hand_resolved_task(tmp_path, monkeypatch, capsys):
    # owner already put it back on the plate; a session reporting "done" afterward must NOT flip it
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    tid = _inflight(tmp_path)
    ss.resolve_in_flight_task(tmp_path, tid, "waiting")  # the manual recovery happened first
    assert resolve_task.main([str(tid), "done"]) == 0    # benign no-op, exits clean
    assert ss.get_task(tmp_path, tid)["status"] == "waiting"
    assert "not in flight" in capsys.readouterr().out


def test_sop_dir_override_beats_env_and_pins_the_library(tmp_path, monkeypatch):
    # ids are per-library autoincrement, so two libraries can both hold a task with the same id.
    # --sop-dir must pin resolution to the intended library even when $SOP_DIR points elsewhere,
    # so a session that lost its env can't resolve the wrong same-id task.
    intended = tmp_path / "intended"
    other = tmp_path / "other"
    intended.mkdir()
    other.mkdir()
    tid_a = _inflight(intended, "the real one")
    tid_b = _inflight(other, "the decoy")
    assert tid_a == tid_b  # same id in both libraries (the collision the pin defends against)
    monkeypatch.setenv("SOP_DIR", str(other))  # env points at the WRONG library
    assert resolve_task.main(["--sop-dir", str(intended), str(tid_a), "done"]) == 0
    assert ss.get_task(intended, tid_a)["status"] == "done"        # the pinned one resolved
    assert ss.get_task(other, tid_b)["status"] == "in_flight"      # the decoy untouched


def test_sop_dir_flag_without_value_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        resolve_task.main(["1", "done", "--sop-dir"])
    assert "--sop-dir needs a directory" in str(exc.value)


def test_rejects_unknown_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    tid = _inflight(tmp_path)
    with pytest.raises(SystemExit) as exc:
        resolve_task.main([str(tid), "blocked"])
    assert "status must be one of" in str(exc.value)
    assert ss.get_task(tmp_path, tid)["status"] == "in_flight"  # unchanged


def test_rejects_wrong_arg_count(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        resolve_task.main([])
    assert "usage:" in str(exc.value)


def test_missing_task_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        resolve_task.main(["999", "done"])
    assert "no task with id 999" in str(exc.value)


def test_non_integer_id_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    with pytest.raises(SystemExit):
        resolve_task.main(["not-a-number", "done"])
