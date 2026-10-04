"""SQLite database setup — raw sqlite3, no ORM needed for this prototype."""
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "portal.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS access_requests (
            id          TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            employee_name TEXT NOT NULL,
            system_id   TEXT NOT NULL,
            system_name TEXT NOT NULL,
            role        TEXT NOT NULL,
            justification TEXT,
            status      TEXT NOT NULL DEFAULT 'pending_approval',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_events (
            id          TEXT PRIMARY KEY,
            request_id  TEXT NOT NULL REFERENCES access_requests(id),
            action      TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            comment     TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  TEXT NOT NULL,
            action      TEXT NOT NULL,
            actor       TEXT NOT NULL,
            detail      TEXT,
            created_at  TEXT NOT NULL
        );
        """)


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
