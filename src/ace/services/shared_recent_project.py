"""One recent project shared by authenticated desktop runtimes on this device."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Iterator


_LOG = logging.getLogger(__name__)
_MAX_PATH_CHARS = 32768


class SharedRecentProjectStore:
    """Serialize concurrent runtimes through SQLite in the launcher's data directory."""

    def __init__(self, runtime_file: Path) -> None:
        self.path = runtime_file.with_name("recent-project.sqlite3")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS recent_project ("
                "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
                "path TEXT NOT NULL, opened_at INTEGER NOT NULL, "
                "revision INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO recent_project "
                "(singleton, path, opened_at, revision) VALUES (1, '', 0, 0)"
            )
            yield conn
            conn.commit()
        finally:
            conn.close()

    def snapshot(self) -> dict[str, object]:
        with self._connection() as conn:
            return self._snapshot(conn)

    @staticmethod
    def _snapshot(conn: sqlite3.Connection) -> dict[str, object]:
        row = conn.execute(
            "SELECT path, opened_at, revision FROM recent_project WHERE singleton = 1"
        ).fetchone()
        return {
            "recent": {"path": row[0], "openedAt": row[1]} if row[0] else None,
            "revision": row[2],
        }

    def read(self) -> dict[str, str | int] | None:
        return self.snapshot()["recent"]

    def set(
        self, path: str, *, opened_at: int | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, object]:
        _check_path(path)
        stamp = int(time.time() * 1000) if opened_at is None else max(0, opened_at)
        with self._connection() as conn:
            updated = conn.execute(
                "UPDATE recent_project SET path = ?, opened_at = ?, "
                "revision = revision + 1 WHERE singleton = 1 "
                "AND (? IS NULL OR revision = ?)",
                (path, stamp, expected_revision, expected_revision),
            )
            return {"applied": updated.rowcount == 1, **self._snapshot(conn)}

    def migrate(self, path: str, *, opened_at: int = 0) -> dict[str, object]:
        """Import legacy browser storage only before any shared choice or clear."""
        _check_path(path)
        with self._connection() as conn:
            updated = conn.execute(
                "UPDATE recent_project SET path = ?, opened_at = ?, "
                "revision = revision + 1 WHERE singleton = 1 AND revision = 0",
                (path, max(0, opened_at)),
            )
            return {"applied": updated.rowcount == 1, **self._snapshot(conn)}

    def clear(
        self, *, if_path: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, object]:
        with self._connection() as conn:
            # Retain the row as a tombstone; a different port must not reimport
            # a stale localStorage value after an explicit clear.
            updated = conn.execute(
                "UPDATE recent_project SET path = '', opened_at = 0, "
                "revision = revision + 1 WHERE singleton = 1 "
                "AND (? IS NULL OR revision = ?) "
                "AND (? IS NULL OR path = ?)",
                (expected_revision, expected_revision, if_path, if_path),
            )
            return {"applied": updated.rowcount == 1, **self._snapshot(conn)}


def _check_path(path: str) -> None:
    if not path or len(path) > _MAX_PATH_CHARS or "\x00" in path:
        raise ValueError("Invalid recent project path")


def remember_recent_project(request, path: str) -> None:
    """Best effort: a history write must never prevent opening a project."""
    store = getattr(request.app.state, "shared_recent_project_store", None)
    if store is None or request.session.get("ace_launcher_authenticated") is not True:
        return
    try:
        store.set(path)
    except (OSError, sqlite3.Error, ValueError):
        _LOG.warning("Could not update shared recent project history")
