"""SmbOS work-state store: the canonical SQLite record for the live-mirror dashboard.

Additive layer. The existing filesystem flows (runs.jsonl, pending/, queue/, work/,
active-runs/, the per-SOP flock) stay canonical for the proven run/approve/queue
machinery and are unchanged. This store holds the NEW work-state the live mirror
needs: tasks on the owner's plate, run metadata, and classifier verdicts.

One shared module, called directly from any process (run_sop, monitors, triage, the
importer, the dashboard server). SQLite runs in WAL mode with a busy_timeout so
concurrent writers from separate processes wait rather than raise "database is
locked".

Liveness is deliberately NOT stored here. A stored "running" flag would lie when a
process is hard-killed, since SQLite has no kernel cleanup. The kernel-held flock
stays the liveness authority; running-vs-stalled is derived from
smbos_lib.active_runs(). This module records run METADATA (what ran, when, cost,
result), never "is it running right now".

Stdlib only, Python 3.9+ (the macOS system python that Claude Desktop uses).
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 4  # bump when SCHEMA_STATEMENTS changes; migrations key off PRAGMA user_version
# v2: partial unique index on (domain, source_ref) so imports can upsert idempotently.
# v3: run.summary holds the run's one-line "what it did" line, surfaced on Recent runs.
# v4: task.action_url -- when set, the dashboard leads with "Open" (this link) over "Pick up".
DB_NAME = "state.db"
BUSY_TIMEOUT_MS = 5000

# Status enums, validated on write so a bad value fails fast instead of silently.
TASK_STATUSES = {"waiting", "in_flight", "done", "dismissed"}
VERDICT_LABELS = {"reply_owed", "ack", "reject", "ignore", "advance"}
SURFACES = {"cc", "api", "cron"}  # where a run was invoked from
RESULT_VALUES = {"ok", "parked", "error", "refused", "skipped"}  # terminal run results

# Schema as individual statements (not one executescript blob) so _migrate can run them
# inside a single held transaction. Future migrations MUST add idempotent statements here
# and bump SCHEMA_VERSION; never use executescript (it force-commits and breaks atomicity).
SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS task (
        id INTEGER PRIMARY KEY,
        domain TEXT NOT NULL,
        kind TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        source_ref TEXT,
        created_at TEXT NOT NULL,   -- ISO-8601 UTC from _now(); callers must not write local/naive times
        updated_at TEXT NOT NULL,
        action_url TEXT             -- optional: when set, the plate row leads with "Open" (this link)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_task_status_priority ON task(status, priority DESC, created_at, id)",
    # v2: a sourced task is unique per (domain, source_ref) so re-imports upsert instead of
    # duplicating. Partial (source_ref IS NOT NULL) so ad-hoc tasks with no source still insert
    # freely. A v1 DB with pre-existing dups is deduped by _apply_migrations BEFORE this index
    # builds (otherwise the build raises and bricks the DB).
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_source ON task(domain, source_ref) WHERE source_ref IS NOT NULL",
    """CREATE TABLE IF NOT EXISTS run (
        id INTEGER PRIMARY KEY,
        sop_id TEXT NOT NULL,
        content_hash TEXT,
        task_id INTEGER REFERENCES task(id),
        surface TEXT NOT NULL,           -- one of SURFACES; validated in start_run()
        result TEXT,                     -- ok|parked|error|refused|skipped, or NULL while open
        cost_usd REAL NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,        -- ISO-8601 UTC from _now()
        ended_at TEXT,
        summary TEXT                     -- v3: one-line "what it did", set by finish_run
    )""",
    "CREATE INDEX IF NOT EXISTS idx_run_started ON run(started_at DESC, id DESC)",
    """CREATE TABLE IF NOT EXISTS verdict (
        id INTEGER PRIMARY KEY,
        thread_id TEXT NOT NULL,
        detector_label TEXT,
        oracle_label TEXT,
        reply_owed INTEGER NOT NULL DEFAULT 0,
        company TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_verdict_thread ON verdict(thread_id)",
)


class StateStoreError(Exception):
    """Schema/version or validation failure in the work-state store."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm_source(source_ref):
    """Empty string means "no source", normalize it to NULL so it is never deduped as a
    real key. (The partial unique index treats '' as a value; a stringifying caller could
    otherwise collide every empty source into one row.)"""
    return None if source_ref in (None, "") else source_ref


def db_path(sop_dir):
    return Path(sop_dir) / DB_NAME


def _migrate(conn):
    """Apply schema migrations atomically, keyed off PRAGMA user_version.

    Concurrency-safe across separate processes. `BEGIN IMMEDIATE` takes the write lock
    up front so exactly one migrator proceeds; the rest wait (busy_timeout), then see the
    bumped version and skip. Schema statements and the user_version bump commit as ONE
    transaction, so a crash can't leave a schema with a stale version, and two processes
    can't both apply a future data migration. Requires the connection in autocommit mode
    (isolation_level=None), set in connect().

    Version-gate: if the DB's user_version is NEWER than this code understands, refuse
    rather than migrate, an old-binary writer (e.g. a cron run_sop from a not-yet-updated
    venv during a rollout) must not corrupt a DB written by newer code.
    """
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver == SCHEMA_VERSION:
        return  # common case: already migrated, take no write lock (no per-call contention)
    if ver > SCHEMA_VERSION:
        raise StateStoreError(
            f"state.db schema is v{ver} but this code understands v{SCHEMA_VERSION}. "
            "Update SmbOS before writing to this database."
        )
    # ver < SCHEMA_VERSION: migrate under a write lock, serialized across processes.
    conn.execute("BEGIN IMMEDIATE")
    try:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]  # re-check under the lock
        if ver < SCHEMA_VERSION:
            _apply_migrations(conn, ver)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()  # e.g. the v2 unique index can't build over conflicting data we failed to dedup
        raise StateStoreError(f"migration to v{SCHEMA_VERSION} failed on conflicting data: {exc}") from exc
    except BaseException:
        conn.rollback()
        raise


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _apply_migrations(conn, from_ver):
    """Bring the schema from `from_ver` up to SCHEMA_VERSION inside the caller's transaction.

    Versioned pre-steps run first (data fixes that must happen before the idempotent base
    schema), then SCHEMA_STATEMENTS (CREATE ... IF NOT EXISTS) creates anything missing.
    """
    # 1 -> 2: an existing v1 table may hold duplicate (domain, source_ref) rows (v1 had no
    # uniqueness). Collapse them, keeping the newest id, BEFORE the v2 unique index is built,
    # or the index creation raises and would otherwise brick the DB on every open. No-op on a
    # fresh DB (the task table doesn't exist yet) and never re-runs (gated on from_ver < 2).
    if from_ver < 2 and _table_exists(conn, "task"):
        conn.execute(
            "DELETE FROM task WHERE source_ref IS NOT NULL AND id NOT IN ("
            " SELECT MAX(id) FROM task WHERE source_ref IS NOT NULL GROUP BY domain, source_ref)"
        )
    # 2 -> 3: add run.summary to an existing run table. CREATE ... IF NOT EXISTS below won't
    # alter an existing table, so add the column here; guarded on the column not already existing
    # so the step is idempotent. No-op on a fresh DB (run table doesn't exist yet; the v3 DDL
    # below creates it with the column).
    if from_ver < 3 and _table_exists(conn, "run"):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(run)").fetchall()]
        if "summary" not in cols:
            conn.execute("ALTER TABLE run ADD COLUMN summary TEXT")
    # 3 -> 4: add task.action_url to an existing task table (CREATE ... IF NOT EXISTS won't alter it).
    # Idempotent (guarded on the column not existing); no-op on a fresh DB (task table created below).
    if from_ver < 4 and _table_exists(conn, "task"):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(task)").fetchall()]
        if "action_url" not in cols:
            conn.execute("ALTER TABLE task ADD COLUMN action_url TEXT")
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)


SETUP_ATTEMPTS = 6  # retries for the transient lock during a concurrent first-creation race


def _open(sop_dir):
    """Open + configure + migrate, with a bounded retry on the transient WAL-setup lock.

    busy_timeout covers normal write contention, but the `journal_mode=WAL` switch during
    a simultaneous first-creation race can still raise "database is locked" before any
    transaction exists (the busy handler does not cover the mode switch). That window is
    microseconds, so a short bounded retry makes concurrent first-creation safe.
    """
    last = None
    for attempt in range(SETUP_ATTEMPTS):
        conn = sqlite3.connect(str(db_path(sop_dir)))
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None  # autocommit; transactions managed explicitly (see _migrate)
        try:
            conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _migrate(conn)
            return conn
        except sqlite3.OperationalError as exc:
            conn.close()
            last = exc
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                time.sleep(0.02 * (attempt + 1))
                continue
            raise
    raise last


@contextmanager
def connect(sop_dir):
    """Open the store in WAL with a busy_timeout, run migrations, yield the connection.

    Safe to call from any process: WAL allows concurrent readers plus one writer, and
    busy_timeout makes a second writer wait (up to BUSY_TIMEOUT_MS) instead of raising.
    Concurrent first-creation is handled by _open's bounded retry.
    """
    conn = _open(sop_dir)
    try:
        yield conn
    finally:
        conn.close()


def data_version(conn):
    """SQLite's change counter; increments on commits from OTHER connections.

    The dashboard reader polls this to decide when to push an SSE update. It does NOT
    change for writes on the SAME connection, so a process that writes must signal its
    own changes directly rather than rely on this counter.
    """
    return conn.execute("PRAGMA data_version").fetchone()[0]


# --- writes (called directly from any process) -----------------------------------

def record_task(sop_dir, domain, kind, subject, status="waiting", priority=0, source_ref=None, action_url=None):
    if status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    source_ref = _norm_source(source_ref)
    now = _now()
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "INSERT INTO task(domain,kind,subject,status,priority,source_ref,created_at,updated_at,action_url)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (domain, kind, subject, status, priority, source_ref, now, now, action_url),
        )
        conn.commit()
        return cur.lastrowid


def upsert_task(sop_dir, domain, kind, subject, status=None, priority=0, source_ref=None, action_url=None):
    """Insert a task, or update the existing one with the same (domain, source_ref).

    Idempotent for imports: re-running with the same source_ref updates that row in place
    (preserving its created_at) instead of duplicating. A NULL source_ref always inserts;
    ad-hoc tasks with no source are not deduped. Returns the task id.

    status=None means "insert as 'waiting', but LEAVE an existing row's status unchanged".
    This is what makes re-import/sync safe: a task you marked done or dismissed is not
    resurrected onto the plate by a later backfill. Pass an explicit status only when the
    source authoritatively owns it (it is then written on both insert and update).
    """
    if status is not None and status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    insert_status = status or "waiting"
    source_ref = _norm_source(source_ref)
    now = _now()
    with connect(sop_dir) as conn:
        if source_ref is None:
            cur = conn.execute(
                "INSERT INTO task(domain,kind,subject,status,priority,source_ref,created_at,updated_at,action_url)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (domain, kind, subject, insert_status, priority, None, now, now, action_url),
            )
            return cur.lastrowid
        # On conflict, always refresh content fields; refresh status ONLY when the caller
        # supplied one, so a locally completed/dismissed task isn't resurrected by a re-import.
        # set_status is a fixed literal (no user input), so the f-string carries no injection risk.
        set_status = "status=excluded.status, " if status is not None else ""
        conn.execute(
            "INSERT INTO task(domain,kind,subject,status,priority,source_ref,created_at,updated_at,action_url)"
            " VALUES(?,?,?,?,?,?,?,?,?)"
            # the partial index's WHERE predicate must be repeated here for ON CONFLICT to match it
            " ON CONFLICT(domain, source_ref) WHERE source_ref IS NOT NULL DO UPDATE SET"
            "   kind=excluded.kind, subject=excluded.subject, " + set_status +
            "   priority=excluded.priority, updated_at=excluded.updated_at, action_url=excluded.action_url",
            (domain, kind, subject, insert_status, priority, source_ref, now, now, action_url),
        )
        row = conn.execute(
            "SELECT id FROM task WHERE domain=? AND source_ref=?", (domain, source_ref)
        ).fetchone()
        return row["id"]


def set_task_status(sop_dir, task_id, status):
    if status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    with connect(sop_dir) as conn:
        conn.execute("UPDATE task SET status=?, updated_at=? WHERE id=?", (status, _now(), task_id))
        conn.commit()


def start_run(sop_dir, sop_id, surface, content_hash=None, task_id=None):
    """Record that a run began. Returns run id. Liveness is the flock's job, not this row."""
    if surface not in SURFACES:
        raise StateStoreError(f"invalid surface {surface!r}; expected one of {sorted(SURFACES)}")
    with connect(sop_dir) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO run(sop_id,content_hash,task_id,surface,started_at) VALUES(?,?,?,?,?)",
                (sop_id, content_hash, task_id, surface, _now()),
            )
        except sqlite3.IntegrityError as exc:
            # task_id must reference an existing task (FK enforced). Wrap so callers see
            # one error type; the importer must insert tasks before the runs that cite them.
            raise StateStoreError(f"start_run: {exc} (task_id={task_id!r} must reference an existing task)") from exc
        conn.commit()
        return cur.lastrowid


def finish_run(sop_dir, run_id, result, cost_usd=0.0, summary=None):
    if result not in RESULT_VALUES:
        raise StateStoreError(f"invalid result {result!r}; expected one of {sorted(RESULT_VALUES)}")
    # summary is the run's one-line "what it did". Coerce defensively (this is a best-effort
    # mirror path and a public store API, so a non-None non-str caller value must not raise),
    # then normalize a blank to NULL so it never renders as an empty summary line; the run keeps
    # showing just its result + cost.
    if summary is not None:
        summary = str(summary).strip() or None
    with connect(sop_dir) as conn:
        conn.execute(
            "UPDATE run SET result=?, cost_usd=?, ended_at=?, summary=? WHERE id=?",
            (result, cost_usd, _now(), summary, run_id),
        )
        conn.commit()


def record_verdict(sop_dir, thread_id, detector_label=None, oracle_label=None, reply_owed=False, company=None):
    if oracle_label is not None and oracle_label not in VERDICT_LABELS:
        raise StateStoreError(f"invalid oracle_label {oracle_label!r}; expected one of {sorted(VERDICT_LABELS)}")
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "INSERT INTO verdict(thread_id,detector_label,oracle_label,reply_owed,company,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (thread_id, detector_label, oracle_label, 1 if reply_owed else 0, company, _now()),
        )
        conn.commit()
        return cur.lastrowid


# --- reads (the dashboard reader) -------------------------------------------------

def plate(sop_dir):
    """The 'on your plate' list: waiting tasks, highest priority first, then oldest first."""
    with connect(sop_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM task WHERE status='waiting' ORDER BY priority DESC, created_at ASC, id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def in_flight(sop_dir):
    """Tasks being worked right now: status 'in_flight', same ordering as the plate.

    A task moves here when its launch opens a session for it; it leaves when the work
    marks it done or dismissed. Mirrors plate() so the dashboard can show both lists.
    """
    with connect(sop_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM task WHERE status='in_flight' ORDER BY priority DESC, created_at ASC, id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def _coerce_task_id(task_id):
    """A task id as an int, or raise StateStoreError. Accepts ints and digit strings (request
    params arrive as strings), but REJECTS bools and non-integral floats: silently truncating
    1.9 -> task 1 would launch/act on a different task than asked, which for an id that gates a
    process spawn is a correctness bug, not a convenience."""
    if isinstance(task_id, bool):
        raise StateStoreError(f"task id is not an integer: {task_id!r}")
    if isinstance(task_id, float):
        if not task_id.is_integer():
            raise StateStoreError(f"task id is not an integer: {task_id!r}")
        return int(task_id)
    try:
        return int(task_id)
    except (TypeError, ValueError):
        raise StateStoreError(f"task id is not an integer: {task_id!r}")


def get_task(sop_dir, task_id):
    """One task row as a dict, or None if no task has that id. Raises StateStoreError if
    task_id is not int-coercible (a malformed id from a request, not a missing row)."""
    task_id = _coerce_task_id(task_id)
    with connect(sop_dir) as conn:
        row = conn.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row is not None else None


def claim_task(sop_dir, task_id):
    """Atomically move a task from 'waiting' to 'in_flight'. Returns True iff THIS call made the
    transition; False if the task wasn't waiting (missing, already picked up, or a concurrent
    claim won the race). The single conditional UPDATE is the launch gate: it closes the
    read-check-act window a double-click or a second client would otherwise drive into two
    launches of one task. Raises StateStoreError on a non-integer id."""
    task_id = _coerce_task_id(task_id)
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "UPDATE task SET status='in_flight', updated_at=? WHERE id=? AND status='waiting'",
            (_now(), task_id),
        )
        return cur.rowcount == 1


def resolve_in_flight_task(sop_dir, task_id, status):
    """Move a task OUT of 'in_flight' to `status` (the dashboard recovery: waiting/done/dismissed),
    atomically and ONLY if it's currently in_flight. Returns True iff this call made the transition;
    False if the task wasn't in_flight (missing, or a concurrent/stale action already resolved it).
    The conditional UPDATE is the recovery gate, the mirror of claim_task: it closes the
    read-check-act window so a stale double-click can't turn an already-recovered task into a
    different state. Raises StateStoreError on a bad status or a non-integer id."""
    if status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    task_id = _coerce_task_id(task_id)
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "UPDATE task SET status=?, updated_at=? WHERE id=? AND status='in_flight'",
            (status, _now(), task_id),
        )
        conn.commit()
        return cur.rowcount == 1


def assert_in_flight(sop_dir, task_id):
    """Atomic in_flight gate with NO side effect: True iff the task is currently in_flight. A
    no-value-change UPDATE (SQLite still reports the matched rowcount), so a caller can gate a
    reopen on the live DB state WITHOUT restarting the liveness grace -- the grace bump
    (touch_in_flight_task) is deferred to a SUCCESSFUL launch, so a failed relaunch can't leave a
    no-marker task reading 'live'. Raises StateStoreError on a non-integer id."""
    task_id = _coerce_task_id(task_id)
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "UPDATE task SET status='in_flight' WHERE id=? AND status='in_flight'",
            (task_id,),
        )
        conn.commit()
        return cur.rowcount == 1


def touch_in_flight_task(sop_dir, task_id):
    """Bump an in_flight task's updated_at, atomically and ONLY if it's currently in_flight. Returns
    True iff it was in_flight (the conditional UPDATE matched a row). The dashboard's 'open session'
    recovery calls this AFTER a successful relaunch to restart the startup grace, so the reopened
    task reads 'live' until its new session's hook records a marker, instead of snapping straight
    back to 'stalled' (its updated_at would otherwise be old). Raises StateStoreError on a
    non-integer id."""
    task_id = _coerce_task_id(task_id)
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "UPDATE task SET updated_at=? WHERE id=? AND status='in_flight'",
            (_now(), task_id),
        )
        conn.commit()
        return cur.rowcount == 1


def recent_runs(sop_dir, limit=50):
    with connect(sop_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM run ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
