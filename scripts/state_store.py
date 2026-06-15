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
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1  # bump when CURRENT_SCHEMA changes; migrations key off PRAGMA user_version
DB_NAME = "state.db"
BUSY_TIMEOUT_MS = 5000

# Status enums, validated on write so a bad value fails fast instead of silently.
TASK_STATUSES = {"waiting", "in_flight", "done", "dismissed"}
VERDICT_LABELS = {"reply_owed", "ack", "reject", "ignore", "advance"}

CURRENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS task (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_status_priority ON task(status, priority DESC, created_at);

CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY,
    sop_id TEXT NOT NULL,
    content_hash TEXT,
    task_id INTEGER REFERENCES task(id),
    surface TEXT NOT NULL,           -- cc | api | cron
    result TEXT,                     -- ok|parked|error|refused|skipped, or NULL while open
    cost_usd REAL NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_started ON run(started_at DESC);

CREATE TABLE IF NOT EXISTS verdict (
    id INTEGER PRIMARY KEY,
    thread_id TEXT NOT NULL,
    detector_label TEXT,
    oracle_label TEXT,
    reply_owed INTEGER NOT NULL DEFAULT 0,
    company TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verdict_thread ON verdict(thread_id);
"""


class StateStoreError(Exception):
    """Schema/version or validation failure in the work-state store."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def db_path(sop_dir):
    return Path(sop_dir) / DB_NAME


def _migrate(conn):
    """Apply schema migrations idempotently, keyed off PRAGMA user_version.

    Version-gate: if the DB's user_version is NEWER than this code understands, refuse
    rather than run an old migration over a newer schema. This is the multi-process /
    strangler-overlap hazard, an old-binary writer (e.g. a cron run_sop from a
    not-yet-updated venv) must not corrupt a DB written by newer code.
    """
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver > SCHEMA_VERSION:
        raise StateStoreError(
            f"state.db schema is v{ver} but this code understands v{SCHEMA_VERSION}. "
            "Update SmbOS before writing to this database."
        )
    if ver < SCHEMA_VERSION:
        conn.executescript(CURRENT_SCHEMA)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.commit()


@contextmanager
def connect(sop_dir):
    """Open the store in WAL with a busy_timeout, run migrations, yield the connection.

    Safe to call from any process: WAL allows concurrent readers plus one writer, and
    busy_timeout makes a second writer wait (up to BUSY_TIMEOUT_MS) instead of raising.
    """
    conn = sqlite3.connect(str(db_path(sop_dir)), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys=ON")
        _migrate(conn)
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

def record_task(sop_dir, domain, kind, subject, status="waiting", priority=0, source_ref=None):
    if status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    now = _now()
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "INSERT INTO task(domain,kind,subject,status,priority,source_ref,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (domain, kind, subject, status, priority, source_ref, now, now),
        )
        conn.commit()
        return cur.lastrowid


def set_task_status(sop_dir, task_id, status):
    if status not in TASK_STATUSES:
        raise StateStoreError(f"invalid task status {status!r}; expected one of {sorted(TASK_STATUSES)}")
    with connect(sop_dir) as conn:
        conn.execute("UPDATE task SET status=?, updated_at=? WHERE id=?", (status, _now(), task_id))
        conn.commit()


def start_run(sop_dir, sop_id, surface, content_hash=None, task_id=None):
    """Record that a run began. Returns run id. Liveness is the flock's job, not this row."""
    with connect(sop_dir) as conn:
        cur = conn.execute(
            "INSERT INTO run(sop_id,content_hash,task_id,surface,started_at) VALUES(?,?,?,?,?)",
            (sop_id, content_hash, task_id, surface, _now()),
        )
        conn.commit()
        return cur.lastrowid


def finish_run(sop_dir, run_id, result, cost_usd=0.0):
    with connect(sop_dir) as conn:
        conn.execute(
            "UPDATE run SET result=?, cost_usd=?, ended_at=? WHERE id=?",
            (result, cost_usd, _now(), run_id),
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
            "SELECT * FROM task WHERE status='waiting' ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def recent_runs(sop_dir, limit=50):
    with connect(sop_dir) as conn:
        rows = conn.execute("SELECT * FROM run ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
