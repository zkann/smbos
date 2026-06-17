"""Picked-up session liveness: the marker helpers in smbos_lib and the session_marker CLI.

Stdlib + pytest. 'Live' is exercised with a real short-lived child process whose pid we check;
'stalled' by killing it. Isolated per tmp_path."""
import subprocess
import sys

import pytest

import smbos_lib as lib
import session_marker


@pytest.fixture
def live_pid():
    """A real, running child process; its pid reads as alive until we reap it."""
    p = subprocess.Popen(["sleep", "30"])
    yield p.pid
    if p.poll() is None:
        p.terminate()
    p.wait()


def test_records_and_reads_live(tmp_path, live_pid):
    lib.record_session(tmp_path, 7, live_pid)
    assert lib.session_state(tmp_path, 7) == "live"


def test_dead_process_reads_stalled(tmp_path):
    p = subprocess.Popen(["sleep", "30"])
    lib.record_session(tmp_path, 7, p.pid)
    p.terminate(); p.wait()           # the session's window closed
    assert lib.session_state(tmp_path, 7) == "stalled"


def test_no_marker_is_none(tmp_path):
    assert lib.session_state(tmp_path, 7) is None  # nothing recorded yet


def test_clear_removes_marker(tmp_path, live_pid):
    lib.record_session(tmp_path, 7, live_pid)
    lib.clear_session(tmp_path, 7)
    assert lib.session_state(tmp_path, 7) is None
    lib.clear_session(tmp_path, 7)  # idempotent: clearing an absent marker is fine


def test_pid_reuse_guard(tmp_path, live_pid):
    # a live pid but a start-time signature that doesn't match => the pid was recycled => stalled
    lib.record_session(tmp_path, 8, live_pid)
    marker = lib._session_marker(tmp_path, 8)
    marker.write_text(f"{live_pid}\nNot The Real Start Time\n", encoding="utf-8")
    assert lib.session_state(tmp_path, 8) == "stalled"


def test_malformed_marker_is_none(tmp_path):
    marker = lib._session_marker(tmp_path, 9)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("not-a-pid\n", encoding="utf-8")
    assert lib.session_state(tmp_path, 9) is None  # never raises on a junk marker


def test_session_marker_cli_records(tmp_path, monkeypatch, live_pid):
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    assert session_marker.main(["record", "7", str(live_pid)]) == 0
    assert lib.session_state(tmp_path, 7) == "live"


@pytest.mark.parametrize("argv", [[], ["record"], ["record", "7"], ["nope", "7", "1"]])
def test_session_marker_cli_ignores_bad_shape(tmp_path, monkeypatch, argv):
    # the hook runs this for EVERY session; a wrong shape must be a silent no-op, not an error
    monkeypatch.setenv("SOP_DIR", str(tmp_path))
    assert session_marker.main(argv) == 0
    assert not (tmp_path / lib.ACTIVE_SESSIONS_DIR).exists()


def test_session_marker_cli_no_sop_dir_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("SOP_DIR", raising=False)
    monkeypatch.setattr(lib, "resolve_sop_dir", lambda *a, **k: None)
    monkeypatch.setattr(session_marker, "resolve_sop_dir", lambda *a, **k: None)
    assert session_marker.main(["record", "7", str(1)]) == 0  # no library: silent no-op
