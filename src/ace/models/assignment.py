"""CRUD operations for assignment table."""

import sqlite3
import uuid
from datetime import datetime, timezone


def _ensure_assignments_no_commit(
    conn: sqlite3.Connection, coder_id: str | None = None
) -> None:
    """Fill missing source/coder pairs within the caller's transaction.

    With no coder_id, reconcile every coder. Existing flags and timestamps
    remain untouched, including when this is called repeatedly.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO assignment (id, source_id, coder_id, flagged, assigned_at, updated_at) "
        "SELECT lower(hex(randomblob(16))), s.id, c.id, 0, ?, ? "
        "FROM source s CROSS JOIN coder c "
        "WHERE (? IS NULL OR c.id = ?) AND NOT EXISTS ("
        "SELECT 1 FROM assignment a WHERE a.source_id = s.id AND a.coder_id = c.id) "
        "ORDER BY s.sort_order, s.rowid, c.rowid "
        "ON CONFLICT(source_id, coder_id) DO NOTHING",
        (now, now, coder_id, coder_id),
    )


def ensure_assignments(conn: sqlite3.Connection, coder_id: str) -> None:
    """Reconcile a coder's assignments, including projects imported previously."""
    _ensure_assignments_no_commit(conn, coder_id)
    conn.commit()


def add_assignment(conn: sqlite3.Connection, source_id: str, coder_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    assignment_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO assignment (id, source_id, coder_id, flagged, assigned_at, updated_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (assignment_id, source_id, coder_id, now, now),
    )
    conn.commit()
    return assignment_id


def set_flagged(
    conn: sqlite3.Connection, source_id: str, coder_id: str, flagged: bool
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE assignment SET flagged = ?, updated_at = ? "
        "WHERE source_id = ? AND coder_id = ?",
        (1 if flagged else 0, now, source_id, coder_id),
    )
    conn.commit()


def get_assignments_for_coder(
    conn: sqlite3.Connection, coder_id: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.*, s.display_id FROM assignment a "
        "JOIN source s ON a.source_id = s.id "
        "WHERE a.coder_id = ? ORDER BY s.sort_order",
        (coder_id,),
    ).fetchall()
