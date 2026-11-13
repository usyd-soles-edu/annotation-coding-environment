"""Per-user UI preferences shared by authenticated desktop runtimes."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterator


_LOG = logging.getLogger(__name__)
_WIDTHS = {"64ch", "72ch", "88ch", "112ch"}
_BOOLEAN_KEYS = {
    "ace-note-open", "ace-grid-collapsed", "ace-applied-codes-collapsed",
}
_KEYS = {
    "ace-sidebar-width", "ace-grid-height", "ace-coding-text-size",
    "ace-coding-text-width", "ace-codebook-cues-enabled",
    *_BOOLEAN_KEYS,
}


def _validate(key: str, value: str | None) -> None:
    if key not in _KEYS:
        raise ValueError("Unknown preference")
    if value is None:
        return
    if key == "ace-sidebar-width":
        valid = value.isascii() and value.isdecimal() and 150 <= int(value) <= 10000
    elif key == "ace-grid-height":
        match = re.fullmatch(r"(\d{2})(?:\.\d{1,2})?vh", value)
        valid = bool(match and 10 <= float(value[:-2]) <= 70)
    elif key == "ace-coding-text-size":
        valid = value.isascii() and value.isdecimal() and 13 <= int(value) <= 32
    elif key == "ace-coding-text-width":
        valid = value in _WIDTHS
    elif key == "ace-codebook-cues-enabled":
        valid = value in {"0", "1"}
    else:
        valid = value == "1"
    if not valid:
        raise ValueError("Invalid preference value")


class SharedPreferencesStore:
    """One SQLite row per preference, with compare-and-set per-key revisions."""

    def __init__(self, runtime_file: Path) -> None:
        self.path = runtime_file.with_name("user-preferences.sqlite3")

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
                "CREATE TABLE IF NOT EXISTS preference ("
                "key TEXT PRIMARY KEY, value TEXT, revision INTEGER NOT NULL)"
            )
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _entry(conn: sqlite3.Connection, key: str) -> dict[str, str | int | None]:
        row = conn.execute(
            "SELECT value, revision FROM preference WHERE key = ?", (key,)
        ).fetchone()
        return {"value": row[0], "revision": row[1]} if row else {
            "value": None, "revision": 0,
        }

    def snapshot(self) -> dict[str, dict[str, str | int | None]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT key, value, revision FROM preference").fetchall()
        return {
            key: {"value": value, "revision": revision}
            for key, value, revision in rows
        }

    def set(
        self, key: str, value: str | None, *, expected_revision: int,
    ) -> dict[str, object]:
        _validate(key, value)
        if expected_revision < 0:
            raise ValueError("Invalid preference revision")
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO preference (key, value, revision) "
                "VALUES (?, NULL, 0)", (key,)
            )
            updated = conn.execute(
                "UPDATE preference SET value = ?, revision = revision + 1 "
                "WHERE key = ? AND revision = ?",
                (value, key, expected_revision),
            )
            return {
                "applied": updated.rowcount == 1,
                "key": key,
                "entry": self._entry(conn, key),
            }

    def migrate(self, key: str, value: str) -> dict[str, object]:
        _validate(key, value)
        with self._connection() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO preference (key, value, revision) "
                "VALUES (?, ?, 1)", (key, value),
            )
            return {
                "applied": inserted.rowcount == 1,
                "key": key,
                "entry": self._entry(conn, key),
            }


def preferences_for_request(request) -> dict | None:
    """Supply pre-paint settings, falling back to browser storage on failure."""
    store = getattr(request.app.state, "shared_preferences_store", None)
    if store is None or request.session.get("ace_launcher_authenticated") is not True:
        return None
    try:
        return store.snapshot()
    except (OSError, sqlite3.Error):
        _LOG.warning("Could not read shared UI preferences")
        return None
