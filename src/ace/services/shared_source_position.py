"""Per-project source positions shared by desktop runtimes on this device."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import logging
import os
from pathlib import Path
import sqlite3
from typing import Iterator


_LOG = logging.getLogger(__name__)


def position_key(project_path: str, project_id: str, coder_id: str) -> str:
    """Identify one project file and coder, including copied files with the same ID."""
    canonical_path = os.path.normcase(os.path.realpath(project_path))
    identity = "\0".join((canonical_path, project_id, coder_id))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class SharedSourcePositionStore:
    """Use SQLite to make concurrent runtime writes atomic; the last write wins."""

    def __init__(self, runtime_file: Path) -> None:
        self.path = runtime_file.with_name("source-positions.sqlite3")

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
                "CREATE TABLE IF NOT EXISTS source_position ("
                "project_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, "
                "revision INTEGER NOT NULL DEFAULT 1)"
            )
            yield conn
            conn.commit()
        finally:
            conn.close()

    def read(self, project_key: str) -> dict[str, str | int] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT source_id, revision FROM source_position WHERE project_key = ?",
                (project_key,),
            ).fetchone()
            return {"source_id": row[0], "revision": row[1]} if row else None

    def set(
        self, project_key: str, source_id: str, *, migrate: bool = False,
    ) -> dict[str, object]:
        if not project_key or not source_id:
            raise ValueError("Invalid source position")
        with self._connection() as conn:
            if migrate:
                changed = conn.execute(
                    "INSERT OR IGNORE INTO source_position (project_key, source_id) "
                    "VALUES (?, ?)",
                    (project_key, source_id),
                )
            else:
                changed = conn.execute(
                    "INSERT INTO source_position (project_key, source_id) VALUES (?, ?) "
                    "ON CONFLICT(project_key) DO UPDATE SET "
                    "source_id = excluded.source_id, revision = revision + 1",
                    (project_key, source_id),
                )
            row = conn.execute(
                "SELECT source_id, revision FROM source_position WHERE project_key = ?",
                (project_key,),
            ).fetchone()
            return {
                "applied": changed.rowcount == 1,
                "source_id": row[0],
                "revision": row[1],
            }


def remember_source_position(request, conn, coder_id: str, source_id: str) -> None:
    """Save before returning a new source; storage failure must not block coding."""
    store = getattr(request.app.state, "shared_source_position_store", None)
    if store is None or request.session.get("ace_launcher_authenticated") is not True:
        return
    from ace.models.project import get_project

    project_path = request.app.state.project_path
    key = position_key(project_path, get_project(conn)["id"], coder_id)
    try:
        store.set(key, source_id)
    except (OSError, sqlite3.Error):
        _LOG.warning("Could not save shared source position")
