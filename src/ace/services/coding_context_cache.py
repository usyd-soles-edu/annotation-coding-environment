"""Reuse project-wide coding data while SQLite reports no external writes."""

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path


class CodingContextCache:
    """Keep one project/coder snapshot behind a persistent SQLite observer.

    ``PRAGMA data_version`` is meaningful only on the same connection. Every
    ACE request and other runtime writes through a different connection, so a
    dedicated observer notices both local and external commits without a scan.
    The observer never holds a read transaction between requests.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path: str | None = None
        self._file_id: tuple[int, int] | None = None
        self._observer: sqlite3.Connection | None = None
        self._snapshot: tuple[str, int, dict] | None = None

    def get(
        self,
        project_path: str,
        coder_id: str,
        load: Callable[[], dict],
    ) -> dict:
        """Return a cached snapshot, rebuilding after any database commit."""
        with self._lock:
            stat = Path(project_path).stat()
            file_id = (stat.st_dev, stat.st_ino)
            if self._path != project_path or self._file_id != file_id:
                self._close_locked()
                self._observer = sqlite3.connect(
                    project_path, check_same_thread=False
                )
                self._observer.execute("PRAGMA query_only = ON")
                self._path = project_path
                self._file_id = file_id

            assert self._observer is not None
            version = self._observer.execute("PRAGMA data_version").fetchone()[0]
            if self._snapshot is not None:
                cached_coder, cached_version, cached_data = self._snapshot
                if cached_coder == coder_id and cached_version == version:
                    return cached_data

            # A concurrent commit during the scan could leave a mixed or stale
            # snapshot. Retry once; if writes continue, serve the fresh read
            # without retaining it as the next request's cache entry.
            data = load()
            after = self._observer.execute("PRAGMA data_version").fetchone()[0]
            if after != version:
                data = load()
                version = after
                after = self._observer.execute("PRAGMA data_version").fetchone()[0]
            if after == version:
                self._snapshot = (coder_id, after, data)
            else:
                self._snapshot = None
            return data

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._observer is not None:
            self._observer.close()
        self._observer = None
        self._path = None
        self._file_id = None
        self._snapshot = None
