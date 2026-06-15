"""Unit tests for the work-state store. Stdlib + pytest; isolated per tmp_path.

Covers migration, the version-gate (the multi-process/strangler hazard), task plate
ordering, run metadata lifecycle, verdict recording, WAL mode, cross-connection change
detection (the data_version signal the dashboard reader polls), and concurrent writers
from separate connections (the module's headline property)."""
import sqlite3
import threading
import time

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


def test_upsert_idempotent_on_source_ref(tmp_path):
    a = ss.upsert_task(tmp_path, "ops", "review", "first", priority=1, source_ref="acme-1")
    b = ss.upsert_task(tmp_path, "ops", "review", "updated", priority=5, source_ref="acme-1")
    assert a == b  # same (domain, source_ref) -> same row, updated in place
    rows = ss.plate(tmp_path)
    assert len(rows) == 1
    assert rows[0]["subject"] == "updated" and rows[0]["priority"] == 5


def test_upsert_null_source_always_inserts(tmp_path):
    ss.upsert_task(tmp_path, "ops", "review", "ad-hoc")
    ss.upsert_task(tmp_path, "ops", "review", "ad-hoc")
    assert len(ss.plate(tmp_path)) == 2  # NULL source_ref is never deduped


def test_upsert_same_source_ref_different_domain_are_distinct(tmp_path):
    ss.upsert_task(tmp_path, "ops", "review", "x", source_ref="s1")
    ss.upsert_task(tmp_path, "billing", "review", "y", source_ref="s1")
    assert len(ss.plate(tmp_path)) == 2  # uniqueness is per (domain, source_ref)


def test_v1_to_v2_migration_adds_unique_index(tmp_path):
    # A pre-existing v1 DB (task table, user_version=1, no idx_task_source) must upgrade
    # to v2 on open: proves the migration machinery upgrades a real older DB, not just fresh.
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.executescript(
        "CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL,"
        " subject TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,"
        " source_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        " PRAGMA user_version=1;"
    )
    raw.commit()
    raw.close()
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_task_source" in idx
    a = ss.upsert_task(tmp_path, "ops", "review", "x", source_ref="s1")
    b = ss.upsert_task(tmp_path, "ops", "review", "x2", source_ref="s1")
    assert a == b  # upsert works on the migrated DB


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


def test_invalid_surface_raises(tmp_path):
    with pytest.raises(ss.StateStoreError):
        ss.start_run(tmp_path, "weekly-report", surface="bogus")


def test_data_version_detects_cross_connection_write(tmp_path):
    # The dashboard reader holds a connection open and polls data_version; a write from
    # a SEPARATE process/connection must bump it so the reader knows to push an update.
    with ss.connect(tmp_path) as reader:
        before = ss.data_version(reader)
        ss.record_task(tmp_path, "ops", "review", "new item")  # its own connection + commit
        after = ss.data_version(reader)
    assert after > before


def test_data_version_unchanged_for_same_connection_write(tmp_path):
    # data_version bumps for OTHER connections' commits, NOT the reader's own writes, so
    # the polling reader must signal its own changes itself (documented in data_version()).
    with ss.connect(tmp_path) as conn:
        before = ss.data_version(conn)
        now = ss._now()
        conn.execute(
            "INSERT INTO task(domain,kind,subject,status,priority,source_ref,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            ("ops", "review", "self-write", "waiting", 0, None, now, now),
        )
        assert ss.data_version(conn) == before


def test_concurrent_writers_from_separate_connections(tmp_path):
    # Headline property: separate processes/connections write at once via WAL +
    # busy_timeout with no "database is locked". Threads with their own connections
    # exercise the same SQLite locking, and also race the first-open migration.
    errors = []

    def writer(tag):
        try:
            for i in range(10):
                ss.record_task(tmp_path, "ops", "review", f"{tag}-{i}")
        except Exception as exc:  # noqa: BLE001 - capture any writer failure for the assert
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"concurrent writers raised: {errors}"
    with ss.connect(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 20


def test_busy_timeout_makes_second_writer_wait(tmp_path):
    # The actual busy_timeout guarantee: a second writer WAITS for a held write lock and
    # then succeeds, rather than immediately raising "database is locked". With
    # busy_timeout=0 this would raise, so this test guards the PRAGMA, not just WAL.
    ss.record_task(tmp_path, "ops", "review", "seed")  # create + migrate first
    result = {}

    def waiter():
        try:
            ss.record_task(tmp_path, "ops", "review", "after-wait")
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["err"] = exc

    with ss.connect(tmp_path) as holder:
        holder.execute("BEGIN IMMEDIATE")  # hold the single WAL write lock
        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.3)  # waiter is now blocked, waiting on busy_timeout (5s)
        holder.execute("COMMIT")  # release; waiter should now proceed
        t.join(timeout=10)

    assert result.get("ok") is True, f"second writer did not wait+succeed: {result.get('err')}"
    assert any(t_["subject"] == "after-wait" for t_ in ss.plate(tmp_path))


def test_start_run_rejects_bogus_task_id(tmp_path):
    # FK is enforced; a run citing a non-existent task fails fast as StateStoreError
    # (not a raw sqlite3.IntegrityError), so callers see one error type.
    with pytest.raises(ss.StateStoreError):
        ss.start_run(tmp_path, "weekly-report", surface="cc", task_id=99999)
    # a NULL task_id (unattached run) is allowed
    assert ss.start_run(tmp_path, "weekly-report", surface="cc") > 0


def test_invalid_result_raises(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    with pytest.raises(ss.StateStoreError):
        ss.finish_run(tmp_path, rid, result="bogus")


def test_migration_rollback_is_atomic(tmp_path, monkeypatch):
    # If a migration fails partway, the whole thing rolls back: no tables, version stays 0.
    # Locks in the atomic-migration fix (a half-applied schema with a stale version is the
    # multi-process corruption hazard the version-gate exists to prevent).
    broken = ss.SCHEMA_STATEMENTS + ("INSERT INTO does_not_exist VALUES (1)",)
    monkeypatch.setattr(ss, "SCHEMA_STATEMENTS", broken)
    with pytest.raises(sqlite3.OperationalError):
        with ss.connect(tmp_path):
            pass
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = {r[0] for r in raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        raw.close()
    assert "task" not in tables  # the earlier CREATEs in the same txn were rolled back
