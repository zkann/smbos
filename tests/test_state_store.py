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


def test_action_url_recorded_and_upserted(tmp_path):
    ss.record_task(tmp_path, "ops", "schedule", "schedule the call", action_url="https://mail.example.com/x")
    assert ss.plate(tmp_path)[0]["action_url"] == "https://mail.example.com/x"
    # upsert refreshes action_url in place
    ss.upsert_task(tmp_path, "ops", "reply", "draft", source_ref="acme-7", action_url="https://d.example.com/y")
    ss.upsert_task(tmp_path, "ops", "reply", "draft", source_ref="acme-7", action_url="https://d.example.com/z")
    row = next(t for t in ss.plate(tmp_path) if t["source_ref"] == "acme-7")
    assert row["action_url"] == "https://d.example.com/z"
    # a task with no action_url reads NULL (the default -> Pick up only)
    ss.record_task(tmp_path, "ops", "task", "do the thing")
    assert next(t for t in ss.plate(tmp_path) if t["subject"] == "do the thing")["action_url"] is None


def test_migration_v3_to_v4_adds_action_url(tmp_path):
    # build a v3-shaped DB (task table WITHOUT action_url) and confirm connect() migrates it in place.
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.executescript(
        "CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL,"
        " subject TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,"
        " source_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        "INSERT INTO task(domain,kind,subject,status,created_at,updated_at)"
        " VALUES('ops','review','old task','waiting','t','t');"
        "PRAGMA user_version=3;")
    raw.commit()
    raw.close()
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        assert "action_url" in [r[1] for r in conn.execute("PRAGMA table_info(task)").fetchall()]
    row = ss.plate(tmp_path)[0]
    assert row["subject"] == "old task" and row["action_url"] is None  # pre-existing row gets NULL


def test_migration_v7_to_v8_adds_provenance_columns(tmp_path):
    # a v7-shaped DB (task table WITHOUT why/producer/sop_id) must migrate in place on open.
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.executescript(
        "CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL,"
        " subject TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,"
        " source_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " action_url TEXT, cwd TEXT, facts TEXT);"
        "INSERT INTO task(domain,kind,subject,status,created_at,updated_at)"
        " VALUES('ops','review','old task','waiting','t','t');"
        "PRAGMA user_version=7;")
    raw.commit()
    raw.close()
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        cols = {r[1] for r in conn.execute("PRAGMA table_info(task)").fetchall()}
        assert {"why", "producer", "sop_id"} <= cols
    row = ss.plate(tmp_path)[0]
    assert row["subject"] == "old task" and row["why"] is None  # pre-existing row gets NULL


def test_provenance_why_refreshes_producer_sopid_set_once(tmp_path):
    # the dossier provenance refresh policy: why REFRESHES on re-import; producer/sop_id are SET-ONCE
    # (COALESCE), so a later sync that changes or omits them never overwrites the originals.
    ss.upsert_task(tmp_path, "ops", "reply", "lease", source_ref="s1",
                   why="reply about the lease date", producer="pipeline-a", sop_id="sop-a")
    ss.upsert_task(tmp_path, "ops", "reply", "lease", source_ref="s1",
                   why="now: confirm the date", producer="pipeline-b", sop_id="sop-b")  # different values
    ss.upsert_task(tmp_path, "ops", "reply", "lease", source_ref="s1", why="latest")    # omits producer/sop_id
    with ss.connect(tmp_path) as conn:
        row = conn.execute("SELECT why, producer, sop_id FROM task WHERE source_ref='s1'").fetchone()
    assert row["why"] == "latest"           # refreshed each time
    assert row["producer"] == "pipeline-a"  # set-once: first value wins, never overwritten or blanked
    assert row["sop_id"] == "sop-a"         # set-once


def test_provenance_set_once_fills_a_null_later(tmp_path):
    # set-once means "first NON-NULL wins": a task created without a producer can still get one later.
    ss.upsert_task(tmp_path, "ops", "reply", "x", source_ref="s1")                          # no producer
    ss.upsert_task(tmp_path, "ops", "reply", "x", source_ref="s1", producer="pipeline-a")   # fills it
    with ss.connect(tmp_path) as conn:
        got = conn.execute("SELECT producer FROM task WHERE source_ref='s1'").fetchone()["producer"]
    assert got == "pipeline-a"


def test_record_task_provenance(tmp_path):
    ss.record_task(tmp_path, "ops", "reply", "x", why="reply about the lease",
                   producer="pipeline-a", sop_id="sop-a")
    row = ss.plate(tmp_path)[0]
    assert row["why"] == "reply about the lease"
    assert row["producer"] == "pipeline-a" and row["sop_id"] == "sop-a"


def test_upsert_without_provenance_leaves_columns_null(tmp_path):
    # regression: existing callers that pass no provenance still work; columns default NULL and the
    # content fields still refresh on re-import (the v8 columns don't disturb existing behavior).
    ss.upsert_task(tmp_path, "ops", "review", "plain", source_ref="s1")
    ss.upsert_task(tmp_path, "ops", "review", "plain v2", source_ref="s1")
    with ss.connect(tmp_path) as conn:
        row = conn.execute("SELECT subject, why, producer, sop_id FROM task WHERE source_ref='s1'").fetchone()
    assert row["subject"] == "plain v2"
    assert row["why"] is None and row["producer"] is None and row["sop_id"] is None


def test_upsert_null_source_always_inserts(tmp_path):
    ss.upsert_task(tmp_path, "ops", "review", "ad-hoc")
    ss.upsert_task(tmp_path, "ops", "review", "ad-hoc")
    assert len(ss.plate(tmp_path)) == 2  # NULL source_ref is never deduped


def test_upsert_preserves_status_when_not_supplied(tmp_path):
    # the trust case: a completed/dismissed task must NOT be resurrected by a re-import
    tid = ss.upsert_task(tmp_path, "ops", "review", "x", source_ref="s1")
    ss.set_task_status(tmp_path, tid, "done")
    ss.upsert_task(tmp_path, "ops", "review", "x (updated)", source_ref="s1")  # status=None -> keep done
    assert ss.plate(tmp_path) == []  # not back on the plate
    with ss.connect(tmp_path) as conn:
        row = conn.execute("SELECT status, subject FROM task WHERE source_ref='s1'").fetchone()
    assert row["status"] == "done" and row["subject"] == "x (updated)"  # content refreshed, status kept


def test_upsert_sets_status_when_explicitly_supplied(tmp_path):
    tid = ss.upsert_task(tmp_path, "ops", "review", "x", source_ref="s1")
    ss.set_task_status(tmp_path, tid, "done")
    ss.upsert_task(tmp_path, "ops", "review", "x", status="waiting", source_ref="s1")  # explicit overrides
    assert len(ss.plate(tmp_path)) == 1


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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_task_source" in idx
    a = ss.upsert_task(tmp_path, "ops", "review", "x", source_ref="s1")
    b = ss.upsert_task(tmp_path, "ops", "review", "x2", source_ref="s1")
    assert a == b  # upsert works on the migrated DB


def test_v1_to_v2_migration_dedups_existing_duplicates(tmp_path):
    # The dangerous case: a v1 DB with duplicate (domain, source_ref) rows. v2's unique index
    # would fail and brick the DB; _apply_migrations must dedup (keep newest id) first.
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.executescript(
        "CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL,"
        " subject TEXT NOT NULL, status TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0,"
        " source_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        " PRAGMA user_version=1;"
    )
    for tid, subj in ((1, "older"), (2, "newer")):
        raw.execute(
            "INSERT INTO task(id,domain,kind,subject,status,priority,source_ref,created_at,updated_at)"
            " VALUES(?,'ops','review',?,'waiting',0,'dup','t','t')", (tid, subj))
    raw.commit()
    raw.close()
    with ss.connect(tmp_path) as conn:  # must NOT raise / brick
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        rows = conn.execute("SELECT subject FROM task WHERE source_ref='dup'").fetchall()
    assert [r["subject"] for r in rows] == ["newer"]  # MAX(id) survived the dedup


def test_v2_to_v3_migration_adds_run_summary_column(tmp_path):
    # A pre-existing v2 DB (run table without summary, user_version=2) must gain run.summary on
    # open, preserving existing run rows. Proves the additive v3 migration upgrades a real DB.
    raw = sqlite3.connect(str(ss.db_path(tmp_path)))
    raw.executescript(
        "CREATE TABLE run (id INTEGER PRIMARY KEY, sop_id TEXT NOT NULL, content_hash TEXT,"
        " task_id INTEGER, surface TEXT NOT NULL, result TEXT, cost_usd REAL NOT NULL DEFAULT 0,"
        " started_at TEXT NOT NULL, ended_at TEXT);"
        " INSERT INTO run(id,sop_id,surface,result,cost_usd,started_at,ended_at)"
        "  VALUES(1,'old-run','cron','ok',0.1,'t','t2');"
        " PRAGMA user_version=2;"
    )
    raw.commit()
    raw.close()
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        cols = {r[1] for r in conn.execute("PRAGMA table_info(run)").fetchall()}
        assert "summary" in cols
        row = conn.execute("SELECT sop_id, result, summary FROM run WHERE id=1").fetchone()
    assert row["sop_id"] == "old-run" and row["result"] == "ok" and row["summary"] is None


def test_empty_source_ref_is_not_deduped(tmp_path):
    ss.record_task(tmp_path, "ops", "review", "a", source_ref="")
    ss.record_task(tmp_path, "ops", "review", "b", source_ref="")
    ss.upsert_task(tmp_path, "ops", "review", "c", source_ref="")
    rows = ss.plate(tmp_path)
    assert len(rows) == 3  # "" normalized to NULL, never deduped
    assert all(r["source_ref"] is None for r in rows)


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


def test_finish_run_persists_summary(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    ss.finish_run(tmp_path, rid, result="ok", cost_usd=0.1, summary="Compiled 4 KPIs, churn up 2%")
    assert ss.recent_runs(tmp_path)[0]["summary"] == "Compiled 4 KPIs, churn up 2%"


def test_finish_run_blank_summary_is_null(tmp_path):
    # an empty/whitespace summary normalizes to NULL so a blank never renders as a summary line
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    ss.finish_run(tmp_path, rid, result="ok", summary="   ")
    assert ss.recent_runs(tmp_path)[0]["summary"] is None


def test_finish_run_default_summary_is_null(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    ss.finish_run(tmp_path, rid, result="ok")
    assert ss.recent_runs(tmp_path)[0]["summary"] is None


def test_finish_run_coerces_non_string_summary(tmp_path):
    # finish_run is a public store API; a non-string summary must coerce, not raise AttributeError
    # (run_sop swallows the mirror error, but a direct caller should get the value recorded).
    rid = ss.start_run(tmp_path, "weekly-report", surface="cc")
    ss.finish_run(tmp_path, rid, result="ok", summary=42)
    assert ss.recent_runs(tmp_path)[0]["summary"] == "42"


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


def test_in_flight_lists_only_in_flight_ordered(tmp_path):
    a = ss.record_task(tmp_path, "ops", "x", "low", priority=1)
    b = ss.record_task(tmp_path, "ops", "x", "high", priority=5)
    ss.record_task(tmp_path, "ops", "x", "stays waiting", priority=9)
    ss.set_task_status(tmp_path, a, "in_flight")
    ss.set_task_status(tmp_path, b, "in_flight")
    rows = ss.in_flight(tmp_path)
    assert [r["subject"] for r in rows] == ["high", "low"]  # priority DESC, same order as plate
    assert all(r["status"] == "in_flight" for r in rows)
    # the high-priority waiting task is on the plate, NOT in the in-flight list
    assert "stays waiting" in [t["subject"] for t in ss.plate(tmp_path)]
    assert "stays waiting" not in [r["subject"] for r in rows]


def test_get_task_returns_row_or_none(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "x", "hello", priority=2)
    row = ss.get_task(tmp_path, tid)
    assert row["id"] == tid and row["subject"] == "hello" and row["status"] == "waiting"
    assert ss.get_task(tmp_path, 999999) is None
    assert ss.get_task(tmp_path, str(tid))["id"] == tid    # request ids arrive as strings
    assert ss.get_task(tmp_path, float(tid))["id"] == tid  # an integral float is fine


def test_get_task_rejects_non_integer_id(tmp_path):
    with ss.connect(tmp_path):
        pass
    # bool and a non-integral float must NOT silently truncate to some other task's id
    for bad in ("not-an-int", None, [1], 1.5, True):
        with pytest.raises(ss.StateStoreError):
            ss.get_task(tmp_path, bad)


def test_claim_task_is_single_winner(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "x", "claim me")
    assert ss.claim_task(tmp_path, tid) is True            # waiting -> in_flight, this call won
    assert ss.get_task(tmp_path, tid)["status"] == "in_flight"
    assert ss.claim_task(tmp_path, tid) is False           # a second claim loses (already in flight)
    assert ss.claim_task(tmp_path, 999999) is False        # no such row, no transition
    with pytest.raises(ss.StateStoreError):
        ss.claim_task(tmp_path, "not-an-int")


def test_resolve_waiting_task_is_single_winner(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "x", "resolve me")            # waiting
    assert ss.resolve_waiting_task(tmp_path, tid, "done") is True       # waiting -> done, this call won
    assert ss.get_task(tmp_path, tid)["status"] == "done"
    assert ss.resolve_waiting_task(tmp_path, tid, "dismissed") is False  # no longer waiting -> no transition
    assert ss.get_task(tmp_path, tid)["status"] == "done"               # unchanged by the losing call
    t2 = ss.record_task(tmp_path, "ops", "x", "dismiss me")
    assert ss.resolve_waiting_task(tmp_path, t2, "dismissed") is True   # waiting -> dismissed
    assert ss.get_task(tmp_path, t2)["status"] == "dismissed"
    inflight = ss.record_task(tmp_path, "ops", "x", "busy", status="in_flight")
    assert ss.resolve_waiting_task(tmp_path, inflight, "done") is False  # gated on waiting only (a Pick up won)
    assert ss.get_task(tmp_path, inflight)["status"] == "in_flight"      # untouched
    assert ss.resolve_waiting_task(tmp_path, 999999, "done") is False    # no such row, no transition
    with pytest.raises(ss.StateStoreError):
        ss.resolve_waiting_task(tmp_path, t2, "bogus")                  # bad status (checked before the id)
    with pytest.raises(ss.StateStoreError):
        ss.resolve_waiting_task(tmp_path, "not-an-int", "done")         # bad id


def test_touch_in_flight_task_gates_on_in_flight_and_bumps_updated_at(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "x", "touch me", status="in_flight")
    before = ss.get_task(tmp_path, tid)["updated_at"]
    assert ss.touch_in_flight_task(tmp_path, tid) is True   # in_flight: matched + bumped
    assert ss.get_task(tmp_path, tid)["updated_at"] >= before  # updated_at advanced (ISO-8601, sortable)
    assert ss.get_task(tmp_path, tid)["status"] == "in_flight"  # status unchanged
    waiting = ss.record_task(tmp_path, "ops", "x", "not in flight")  # waiting
    assert ss.touch_in_flight_task(tmp_path, waiting) is False  # not in_flight: no match
    assert ss.touch_in_flight_task(tmp_path, 999999) is False   # no such row
    with pytest.raises(ss.StateStoreError):
        ss.touch_in_flight_task(tmp_path, "not-an-int")


def test_assert_in_flight_gates_without_side_effect(tmp_path):
    tid = ss.record_task(tmp_path, "ops", "x", "gate me", status="in_flight")
    before = ss.get_task(tmp_path, tid)["updated_at"]
    assert ss.assert_in_flight(tmp_path, tid) is True            # in_flight: gate passes
    assert ss.get_task(tmp_path, tid)["updated_at"] == before    # NO side effect: updated_at untouched
    assert ss.get_task(tmp_path, tid)["status"] == "in_flight"
    waiting = ss.record_task(tmp_path, "ops", "x", "waiting")
    assert ss.assert_in_flight(tmp_path, waiting) is False       # not in_flight: gate fails
    assert ss.assert_in_flight(tmp_path, 999999) is False        # no such row
    with pytest.raises(ss.StateStoreError):
        ss.assert_in_flight(tmp_path, "not-an-int")


def test_facts_round_trips(tmp_path):
    facts = '[{"label":"Received","value":"2d ago","inline":true}]'
    ss.record_task(tmp_path, "ops", "task", "with facts", facts=facts)
    assert ss.plate(tmp_path)[0]["facts"] == facts
    ss.upsert_task(tmp_path, "ops", "task", "x", source_ref="s1", facts='[{"label":"A","value":"1"}]')
    ss.upsert_task(tmp_path, "ops", "task", "x", source_ref="s1", facts='[{"label":"A","value":"2"}]')
    row = next(t for t in ss.plate(tmp_path) if t["source_ref"] == "s1")
    assert row["facts"] == '[{"label":"A","value":"2"}]'


def test_routing_store_idempotent_and_lanes(tmp_path):
    # first route wins; a re-route is a no-op (returns False) and does NOT clobber lane/status
    assert ss.record_route(tmp_path, "email", "t1", "action", consumer="plate", why="reply",
                           payload={"action": "Reply to A"}) is True
    assert ss.record_route(tmp_path, "email", "t1", "job") is False        # re-route ignored
    assert ss.routed_ids(tmp_path, "email") == {"t1"}
    rows = ss.lane_items(tmp_path, "action")                                # status defaults to "routed"
    assert len(rows) == 1 and rows[0]["item_id"] == "t1" and rows[0]["consumer"] == "plate"
    import json
    assert json.loads(rows[0]["payload"])["action"] == "Reply to A"        # dict payload -> JSON
    # lifecycle: routed -> consumed drops it out of the routed slice
    ss.set_route_status(tmp_path, "email", "t1", "consumed")
    assert ss.lane_items(tmp_path, "action") == []
    assert len(ss.lane_items(tmp_path, "action", status="consumed")) == 1


def test_routing_store_cross_source_no_collision(tmp_path):
    assert ss.record_route(tmp_path, "email", "x", "action") is True
    assert ss.record_route(tmp_path, "slack", "x", "action") is True       # same id, different source
    assert ss.routed_ids(tmp_path, "email") == {"x"} and ss.routed_ids(tmp_path, "slack") == {"x"}


def test_routing_store_validation(tmp_path):
    import pytest
    with pytest.raises(ss.StateStoreError):
        ss.record_route(tmp_path, "", "id", "action")          # empty source
    with pytest.raises(ss.StateStoreError):
        ss.record_route(tmp_path, "email", "", "action")       # empty item_id
    with pytest.raises(ss.StateStoreError):
        ss.set_route_status(tmp_path, "email", "x", "bogus")   # bad status


def test_routed_item_table_present_on_fresh_db(tmp_path):
    with ss.connect(tmp_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ss.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "routed_item" in tables
