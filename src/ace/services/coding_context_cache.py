"""Reuse project-wide coding data while SQLite reports no external writes."""

import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

_MAX_SENTENCE_CHARS = 250_000
_MAX_SENTENCE_UNITS = 10_000


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
        self._sentence_units: OrderedDict[
            tuple[str, bytes, tuple[tuple[int, int], ...]],
            tuple[tuple[dict, ...], int],
        ] = OrderedDict()
        self._sentence_chars = 0

    def get(
        self,
        project_path: str,
        coder_id: str,
        load: Callable[[], dict],
    ) -> dict:
        """Return a cached snapshot, rebuilding after any database commit."""
        with self._lock:
            self._observe_project_locked(project_path)
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

    def get_sentence_units(
        self,
        project_path: str,
        source_id: str,
        text: str,
        heading_spans: tuple[tuple[int, int], ...],
    ) -> list[dict]:
        """Reuse costly segmentation for unchanged source text within this project.

        Return fresh dictionaries because callers may later modify their units.
        Short sources do not benefit enough to occupy the cache.
        """
        from ace.services.text_splitter import split_into_units

        if len(text) < 1024 or len(text) > _MAX_SENTENCE_CHARS:
            return split_into_units(text, heading_spans)

        key = (source_id, sha256(text.encode("utf-8")).digest(), heading_spans)
        with self._lock:
            self._observe_project_locked(project_path)
            file_id = self._file_id
            cached = self._sentence_units.get(key)
            if cached is not None:
                self._sentence_units.move_to_end(key)
                return [unit.copy() for unit in cached[0]]

        units = split_into_units(text, heading_spans)
        if len(units) > _MAX_SENTENCE_UNITS:
            return units

        with self._lock:
            try:
                stat = Path(project_path).stat()
            except OSError:
                # A project can be moved or replaced while this request is
                # splitting text already read from its database connection.
                return units
            current_file_id = (stat.st_dev, stat.st_ino)
            if (
                self._path == project_path
                and self._file_id == file_id == current_file_id
                and key not in self._sentence_units
            ):
                while self._sentence_chars + len(text) > _MAX_SENTENCE_CHARS:
                    _, (_, removed_chars) = self._sentence_units.popitem(last=False)
                    self._sentence_chars -= removed_chars
                self._sentence_units[key] = (tuple(unit.copy() for unit in units), len(text))
                self._sentence_chars += len(text)
        return units

    def _observe_project_locked(self, project_path: str) -> None:
        stat = Path(project_path).stat()
        file_id = (stat.st_dev, stat.st_ino)
        if self._path != project_path or self._file_id != file_id:
            self._close_locked()
            self._observer = sqlite3.connect(project_path, check_same_thread=False)
            self._observer.execute("PRAGMA query_only = ON")
            self._path = project_path
            self._file_id = file_id

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
        self._sentence_units.clear()
        self._sentence_chars = 0
