"""Unit tests for the work-state store. Stdlib + pytest; isolated per tmp_path.

Covers migration, the version-gate (the multi-process/strangler hazard), task plate
ordering, run metadata lifecycle, verdict recording, WAL mode, and cross-connection
change detection (the data_version signal the dashboard reader polls)."""
import sqlite3

import pytest

import state_store as ss


def test_fresh_db_migrates_and_creates_tables(tmp_path):
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"task", "run", "verdict"} <= tables


def test_wal_mode_enabled(tmp_path):
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_version_gate_refuses_newer_db(tmp_path):
    # The strangler/multi-process hazard: an old binary must NOT migrate a newer DB.
    with ss.connect(tmp_path):
        pass  # creates the DB at SCHEMA_VERSION
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.execute("PRAGMA user_version=999")
    raw.commit()
    raw.close()
    with pytest.raises(ss.StateStoreError):
        with ss.connect(tmp_path):
            pass


def test_record_task_and_plate_ordering(tmp_path):
    ss.record_task(tmp_path, "ops", "review", "low priority, older", priority=1)
    ss.record_task(tmp_path, "ops", "review", "high priority", priority=5)
    ss.record_task(tmp_path, "ops", "review", "low priority, newer", priority=1)
    subjects = [t["subject"] for t in ss.plate(tmp_path)]
    # priority DESC first, then created_at ASC within the same priority
    assert subjects == ["high priority", "low priority, older", "low priority, newer"]


def test_plate_excludes_non_waiting(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "review", "started", status="waiting")
    ss.record_task(tmp_path, "ops", "review", "also waiting")
    ss.set_task_status(tmp_path, tid, "in_flight")
    subjects = [t["subject"] for t in ss.plate(tmp_path)]
    assert subjects == ["also waiting"]


def test_invalid_task_status_raises(tmp_path):
    with pytest.raises(ss.StateStoreError):
        ss.record_task(tmp_path, "ops", "review", "x", status="bogus")
    tid = ss.record_task(tmp_path, "ops", "review", "x")
    with pytest.raises(ss.StateStoreError):
        ss.set_task_status(tmp_path, tid, "bogus")


def test_run_metadata_lifecycle(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    open_run = ss.recent_runs(tmp_path)[0]
    assert open_run["id"] == rid and open_run["result"] is None and open_run["ended_at"] is None
    ss.finish_run(tmp_path, rid, result="ok", cost_usd=0.42)
    done = ss.recent_runs(tmp_path)[0]
    assert done["result"] == "ok" and done["cost_usd"] == 0.42 and done["ended_at"] is not None


def test_record_verdict_coerces_reply_owed_and_validates_label(tmp_path):
    ss.record_verdict(tmp_path, "thr-1", detector_label="company", oracle_label="reply_owed",
                      reply_owed=True, company="Acme")
    with ss.connect(tmp_path) as conn:
        row = conn.execute("SELECT reply_owed, company FROM verdict WHERE thread_id='thr-1'").fetchone()
    assert row["reply_owed"] == 1 and row["company"] == "Acme"
    with pytest.raises(ss.StateStoreError):
        ss.record_verdict(tmp_path, "thr-2", oracle_label="not-a-label")


def test_data_version_detects_cross_connection_write(tmp_path):
    # The dashboard reader holds a connection open and polls data_version; a write from
    # a SEPARATE process/connection must bump it so the reader knows to push an update.
    with ss.connect(tmp_path) as reader:
        before = ss.data_version(reader)
        ss.record_task(tmp_path, "ops", "review", "new item")  # its own connection + commit
        after = ss.data_version(reader)
    assert after > before
