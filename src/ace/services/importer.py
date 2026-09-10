"""Import sources from CSV/Excel files and text file folders."""

import csv
import hashlib
import os
import random
import sqlite3
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from ace.models.source import _add_source_no_commit

_CSV_ENCODINGS = ("utf-8", "cp1252", "latin-1")
_TEXT_EXTENSIONS = ("*.txt", "*.md")


@dataclass(frozen=True)
class ImportResult:
    created: int
    duplicate_skipped: int
    empty_skipped: int
    created_ids: list[str]

    def __iter__(self):
        yield self.created
        yield self.duplicate_skipped
        yield self.created_ids


@dataclass(frozen=True)
class _SourceCandidate:
    display_id: str
    content_text: str
    source_type: str
    filename: str | None = None
    source_column: str | None = None
    metadata: dict | None = None
    section_heading_spans: list[tuple[int, int]] | None = None
    empty: bool = False


def _existing_display_ids(conn: sqlite3.Connection) -> set[str]:
    """Return the set of display_ids already present in the source table."""
    return {row[0] for row in conn.execute("SELECT display_id FROM source")}


def count_already_present(conn: sqlite3.Connection, folder: str | Path) -> int:
    """Count text files in ``folder`` whose stem is already a source display_id."""
    existing = _existing_display_ids(conn)
    return sum(1 for f in _list_text_files(Path(folder)) if f.stem in existing)


def import_csv(
    conn: sqlite3.Connection,
    path: str | Path,
    id_column: str,
    text_columns: list[str],
    tabular_data: tuple[list[dict], list[str]] | None = None,
) -> ImportResult:
    """Import rows from a CSV or Excel file as sources.

    Each row becomes one source. When multiple text columns are selected,
    their values are combined as labelled sections in source order.
    Non-ID/non-text columns are stored as metadata_json.

    Rows whose ``display_id`` already exists in the ``source`` table are
    skipped (the existing text is preserved). Returns
    ``(created, skipped, created_ids)`` where ``created_ids`` is the list of
    new source ids (used by the 'Remove last import' button).
    """
    path = Path(path)
    rows, columns = tabular_data if tabular_data is not None else read_tabular(path)

    meta_columns = [c for c in columns if c != id_column and c not in text_columns]
    empty_skipped = 0
    candidates: list[_SourceCandidate] = []

    for row in rows:
        raw_display_id = row[id_column]
        has_selected_text = _row_has_selected_text(row, text_columns)
        if not has_selected_text and _is_blank_value(raw_display_id):
            empty_skipped += 1
            continue
        display_id = _validated_display_id(raw_display_id)
        metadata = (
            {c: row[c] for c in meta_columns}
            if meta_columns and has_selected_text
            else None
        )
        if has_selected_text:
            content_text, section_heading_spans = _combine_text_columns(
                row, text_columns
            )
        else:
            content_text, section_heading_spans = "", None

        candidates.append(
            _SourceCandidate(
                display_id=display_id,
                content_text=content_text,
                source_type="row",
                filename=path.name,
                source_column=None,
                metadata=metadata,
                section_heading_spans=section_heading_spans,
                empty=not has_selected_text,
            )
        )

    return _insert_candidates(conn, candidates, empty_skipped=empty_skipped)


def _row_has_selected_text(row: dict, text_columns: list[str]) -> bool:
    return any(
        value is not None and str(value).strip() != ""
        for value in (row.get(col) for col in text_columns)
    )


def _combine_text_columns(
    row: dict,
    text_columns: list[str],
) -> tuple[str, list[tuple[int, int]]]:
    if len(text_columns) == 1:
        value = row[text_columns[0]]
        return ("" if value is None else str(value)), []

    parts: list[str] = []
    heading_spans: list[tuple[int, int]] = []
    offset = 0
    for index, col in enumerate(text_columns):
        if index:
            parts.append("\n\n")
            offset += 2

        title = str(col)
        heading_start = offset
        parts.append(title)
        offset += len(title)
        if title:
            heading_spans.append((heading_start, offset))

        value = row[col]
        text = "" if value is None else str(value)
        parts.extend(("\n", text))
        offset += 1 + len(text)

    return "".join(parts), heading_spans


def _list_text_files(folder: Path) -> list[Path]:
    """Return regular text files (.txt, .md) in folder, sorted by name."""
    files = []
    for pattern in _TEXT_EXTENSIONS:
        files.extend(p for p in folder.glob(pattern) if p.is_file())
    files.sort(key=lambda p: p.name)
    return files


def import_text_files(
    conn: sqlite3.Connection,
    folder: str | Path,
) -> ImportResult:
    """Import text files (.txt, .md) from a folder as sources.

    Each file becomes one source with ``display_id`` = filename stem. Files
    whose stem already exists in the ``source`` table are skipped (the
    existing text is preserved). Returns ``(created, skipped, created_ids)``
    where ``created_ids`` is the list of new source ids (used by the
    'Remove last import' button).
    """
    candidates: list[_SourceCandidate] = []
    for txt_path in _list_text_files(Path(folder)):
        display_id = _validated_display_id(txt_path.stem)
        content = _read_text_file(txt_path)
        candidates.append(
            _SourceCandidate(
                display_id=display_id,
                content_text=content,
                source_type="file",
                filename=txt_path.name,
                empty=not content.strip(),
            )
        )

    return _insert_candidates(conn, candidates)


# ---------------------------------------------------------------------------
# Folder import preview seams: recursive scan, classification, manifest.
#
# These seams only observe the folder and existing source labels. They never
# write to SQLite and never sample randomly; the confirmation path is the
# sole mutation route for the folder-import workflow.
# ---------------------------------------------------------------------------

FOLDER_CATEGORY_READY = "supported-ready"
FOLDER_CATEGORY_UNSUPPORTED = "unsupported"
FOLDER_CATEGORY_UNREADABLE = "unreadable"
FOLDER_CATEGORY_EMPTY = "empty"
FOLDER_CATEGORY_DUPLICATE = "duplicate"

_FOLDER_CATEGORIES = (
    FOLDER_CATEGORY_READY,
    FOLDER_CATEGORY_UNSUPPORTED,
    FOLDER_CATEGORY_UNREADABLE,
    FOLDER_CATEGORY_EMPTY,
    FOLDER_CATEGORY_DUPLICATE,
)

_FOLDER_SUPPORTED_SUFFIXES = frozenset({".txt", ".md"})


@dataclass(frozen=True)
class FolderImportFingerprint:
    """Immutable identity of a ready file as it was at preview time.

    Content hash plus size and mtime_ns lets confirmation detect files that
    were edited in place; the filesystem identity (device, inode) additionally
    detects replacements that preserve size and mtime.
    """

    content_sha256: str
    size: int
    mtime_ns: int
    device: int
    inode: int


@dataclass(frozen=True)
class FolderImportEntry:
    """One examined regular folder file, classified into exactly one category.

    Hidden paths and non-regular entries are rejected before totals and never
    become entries. ``content_text`` and ``fingerprint`` are populated only
    for ready entries; ``detail`` carries a short, path-free reason for the
    non-importable categories.
    """

    relative_path: str
    display_id: str
    category: str
    content_text: str = ""
    fingerprint: FolderImportFingerprint | None = None
    detail: str | None = None


@dataclass(frozen=True)
class FolderImportManifest:
    """Saved snapshot of one reviewed folder preview.

    Confirmation consumes this manifest and must never rescan the folder:
    files added after the preview are excluded from the confirmed batch.
    """

    folder: str
    entries: tuple[FolderImportEntry, ...]

    @property
    def ready_entries(self) -> tuple[FolderImportEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.category == FOLDER_CATEGORY_READY
        )

    @property
    def counts(self) -> Mapping[str, int]:
        """Derived, read-only category counts over the immutable entries."""
        return MappingProxyType(count_folder_import_categories(self.entries))


@dataclass(frozen=True)
class FolderImportPreview:
    """User-facing aggregate over one saved folder-import manifest.

    Aggregates derive from the manifest's immutable entries, so they cannot
    drift from the reviewed data nor be mutated after the preview.
    """

    manifest: FolderImportManifest

    @property
    def total_files(self) -> int:
        return len(self.manifest.entries)

    @property
    def counts(self) -> Mapping[str, int]:
        return self.manifest.counts


@dataclass(frozen=True)
class FolderImportRepreviewRequired:
    """Refused folder-import confirmation; a new preview is required.

    Returned by ``confirm_folder_import`` when a saved ready entry no longer
    matches the folder at confirmation time — changed, deleted, unreadable,
    or saved content that cannot be verified. No database writes have
    occurred. ``detail`` is a short, path-free reason; ``relative_path``
    identifies the offending reviewed entry.
    """

    relative_path: str
    detail: str


def count_folder_import_categories(
    entries: Iterable[FolderImportEntry],
) -> dict[str, int]:
    """Count entries per category; all five categories are always present."""
    counts = dict.fromkeys(_FOLDER_CATEGORIES, 0)
    for entry in entries:
        counts[entry.category] += 1
    return counts


def _is_hidden_component(name: str) -> bool:
    """Dot-prefixed names are hidden and excluded from the entire scan."""
    return name.startswith(".")


def _is_regular_file(path: Path) -> bool:
    """True only for true regular files: symlinks, FIFOs, devices fail."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _iter_regular_folder_files(folder: Path) -> list[Path]:
    """Recursively list regular, non-hidden files under ``folder``.

    Ordered deterministically by POSIX-style relative path. Hidden files,
    hidden directory subtrees, and every non-regular entry (symlinks, FIFOs,
    devices, directories themselves) are rejected before totals.
    """
    found: list[Path] = []
    for root, dir_names, file_names in os.walk(folder, followlinks=False):
        dir_names[:] = sorted(
            name for name in dir_names if not _is_hidden_component(name)
        )
        for name in file_names:
            if _is_hidden_component(name):
                continue
            candidate = Path(root) / name
            if _is_regular_file(candidate):
                found.append(candidate)
    found.sort(key=lambda path: path.relative_to(folder).as_posix())
    return found


def _is_supported_folder_file(path: Path) -> bool:
    """Recognise supported suffixes case-insensitively (.txt, .md, .TXT, .MD)."""
    return path.suffix.lower() in _FOLDER_SUPPORTED_SUFFIXES


def _read_folder_file_bytes(path: Path) -> bytes:
    """Read one candidate's raw bytes; classification handles read failures."""
    return path.read_bytes()


def _fingerprint_bytes(path: Path, data: bytes) -> FolderImportFingerprint:
    """Fingerprint raw content bytes plus immutable identity metadata."""
    stat_result = path.lstat()
    return FolderImportFingerprint(
        content_sha256=hashlib.sha256(data).hexdigest(),
        size=stat_result.st_size,
        mtime_ns=stat_result.st_mtime_ns,
        device=stat_result.st_dev,
        inode=stat_result.st_ino,
    )


def _unreadable_detail(exc: Exception) -> str:
    """Short, path-free reason for an unreadable classification."""
    if isinstance(exc, UnicodeDecodeError):
        return "file is not valid UTF-8"
    return f"file could not be read ({type(exc).__name__})"


def _classify_folder_file(
    path: Path,
    relative_path: str,
    existing_ids: set[str],
) -> FolderImportEntry:
    """Classify one examined regular file into exactly one category.

    Precedence matches confirmed import accounting: unsupported is decided
    before reading, then unreadable, duplicate, empty, and finally ready.
    ``existing_ids`` covers database labels plus display IDs already claimed
    by ready entries earlier in the same deterministic scan, so later
    same-label files classify duplicate exactly as confirmation skips them.
    """
    display_id = path.stem
    if not _is_supported_folder_file(path):
        return FolderImportEntry(
            relative_path=relative_path,
            display_id=display_id,
            category=FOLDER_CATEGORY_UNSUPPORTED,
            detail=f"unsupported suffix '{path.suffix.lower()}'",
        )
    try:
        data = _read_folder_file_bytes(path)
        text = data.decode("utf-8")
        fingerprint = _fingerprint_bytes(path, data)
    except (OSError, UnicodeDecodeError) as exc:
        return FolderImportEntry(
            relative_path=relative_path,
            display_id=display_id,
            category=FOLDER_CATEGORY_UNREADABLE,
            detail=_unreadable_detail(exc),
        )
    if display_id in existing_ids:
        return FolderImportEntry(
            relative_path=relative_path,
            display_id=display_id,
            category=FOLDER_CATEGORY_DUPLICATE,
            detail="label already exists",
        )
    if not text.strip():
        return FolderImportEntry(
            relative_path=relative_path,
            display_id=display_id,
            category=FOLDER_CATEGORY_EMPTY,
            detail="file has no text content",
        )
    return FolderImportEntry(
        relative_path=relative_path,
        display_id=display_id,
        category=FOLDER_CATEGORY_READY,
        content_text=text,
        fingerprint=fingerprint,
    )


def build_folder_import_preview(
    folder: str | Path,
    existing_ids: set[str],
) -> FolderImportPreview:
    """Classify every examined regular file under ``folder`` without side effects.

    Pure seam: reads the filesystem and the supplied existing-label set only;
    never touches SQLite and never samples randomly. Duplicate comparison is
    against ``existing_ids`` plus labels claimed earlier in this scan, so only
    the first entry per display ID (deterministic relative-path order)
    classifies ready and later collisions classify duplicate — matching
    confirmed import accounting.
    """
    folder = Path(folder)
    claimed_ids = set(existing_ids)
    entries: list[FolderImportEntry] = []
    for path in _iter_regular_folder_files(folder):
        entry = _classify_folder_file(
            path,
            path.relative_to(folder).as_posix(),
            claimed_ids,
        )
        if entry.category == FOLDER_CATEGORY_READY:
            claimed_ids.add(entry.display_id)
        entries.append(entry)
    manifest = FolderImportManifest(folder=str(folder), entries=tuple(entries))
    return FolderImportPreview(manifest=manifest)


def preview_folder_import(
    conn: sqlite3.Connection,
    folder: str | Path,
) -> FolderImportPreview:
    """Build a read-only preview manifest for one folder import.

    Reads existing source labels to classify duplicates but performs no
    database writes and opens no import transaction.
    """
    existing_ids = _existing_display_ids(conn)
    return build_folder_import_preview(folder, existing_ids)


def confirm_folder_import(
    conn: sqlite3.Connection,
    manifest: FolderImportManifest,
) -> ImportResult | FolderImportRepreviewRequired:
    """Revalidate a saved manifest's ready files, then import them atomically.

    Iterates only the manifest's supported-ready entries — the folder is never
    rescanned, so files added after the preview cannot join the batch. Each
    ready file is fresh-read and its fingerprint compared before any
    transaction begins; a changed, deleted, unreadable, or unverifiable ready
    file returns ``FolderImportRepreviewRequired`` with no writes and no
    insertion attempt. Validated candidates are inserted through the single
    ``BEGIN IMMEDIATE`` batch in ``_insert_candidates``, which keeps duplicate
    detection inside the transaction and rolls back on every exception.

    Confirmed accounting preserves the reviewed manifest: manifest-level
    duplicate and empty counts are carried into the result, and any label
    claimed by another source between preview and commit is still skipped
    inside the transaction. Unavailable or expired manifest tokens are a
    route-layer concern and are rejected the same way (re-preview required).
    """
    candidates: list[_SourceCandidate] = []
    for entry in manifest.ready_entries:
        if entry.fingerprint is None:
            return FolderImportRepreviewRequired(
                relative_path=entry.relative_path,
                detail="saved file content is unavailable",
            )
        path = Path(manifest.folder) / entry.relative_path
        try:
            data = _read_folder_file_bytes(path)
            text = data.decode("utf-8")
            fingerprint = _fingerprint_bytes(path, data)
        except FileNotFoundError:
            return FolderImportRepreviewRequired(
                relative_path=entry.relative_path,
                detail="file is missing",
            )
        except (OSError, UnicodeDecodeError) as exc:
            return FolderImportRepreviewRequired(
                relative_path=entry.relative_path,
                detail=_unreadable_detail(exc),
            )
        if fingerprint != entry.fingerprint:
            return FolderImportRepreviewRequired(
                relative_path=entry.relative_path,
                detail="file changed since preview",
            )
        candidates.append(
            _SourceCandidate(
                display_id=entry.display_id,
                content_text=text,
                source_type="file",
                filename=path.name,
                empty=not text.strip(),
            )
        )

    result = _insert_candidates(
        conn,
        candidates,
        empty_skipped=manifest.counts[FOLDER_CATEGORY_EMPTY],
    )
    return ImportResult(
        created=result.created,
        duplicate_skipped=(
            result.duplicate_skipped + manifest.counts[FOLDER_CATEGORY_DUPLICATE]
        ),
        empty_skipped=result.empty_skipped,
        created_ids=result.created_ids,
    )


def _is_blank_value(value: object) -> bool:
    return value is None or not str(value).strip()


def _validated_display_id(value: object) -> str:
    """Return a source label, rejecting missing and whitespace-only values."""
    if _is_blank_value(value):
        raise ValueError("Source labels cannot be blank.")
    return str(value)


def _insert_candidates(
    conn: sqlite3.Connection,
    candidates: list[_SourceCandidate],
    empty_skipped: int = 0,
) -> ImportResult:
    """Insert one prepared import batch atomically in candidate order."""
    if not candidates:
        return ImportResult(0, 0, empty_skipped, [])
    if conn.in_transaction:
        raise sqlite3.OperationalError(
            "Cannot import sources inside an existing transaction."
        )

    created_ids: list[str] = []
    duplicate_skipped = 0
    transaction_started = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        transaction_started = True
        existing = _existing_display_ids(conn)
        for candidate in candidates:
            if candidate.display_id in existing:
                duplicate_skipped += 1
                continue
            if candidate.empty:
                empty_skipped += 1
                continue
            created_ids.append(
                _add_source_no_commit(
                    conn,
                    display_id=candidate.display_id,
                    content_text=candidate.content_text,
                    source_type=candidate.source_type,
                    filename=candidate.filename,
                    source_column=candidate.source_column,
                    metadata=candidate.metadata,
                    section_heading_spans=candidate.section_heading_spans,
                )
            )
            existing.add(candidate.display_id)
        conn.commit()
    except Exception:
        if transaction_started:
            conn.rollback()
        raise
    return ImportResult(
        len(created_ids), duplicate_skipped, empty_skipped, created_ids
    )


def get_random_previews(
    folder: str | Path,
    limit: int = 5,
    max_chars: int = 1200,
) -> tuple[int, list[dict]]:
    """Return total text-file count plus a bounded random preview sample."""
    files = _list_text_files(Path(folder))
    total = len(files)
    if total == 0:
        return 0, []

    sample = random.sample(files, min(limit, total))
    previews = []
    for path in sample:
        content = _read_text_file(path)
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        previews.append(
            {
                "filename": path.name,
                "snippet": content,
                "size_label": _format_size(path.stat().st_size),
            }
        )
    return total, previews


def _format_size(size: int) -> str:
    """Return a compact binary size label."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        value = size / 1024
        return f"{value:.1f} KB".replace(".0 KB", " KB")
    value = size / (1024 * 1024)
    return f"{value:.1f} MB".replace(".0 MB", " MB")


def read_tabular(path: Path) -> tuple[list[dict], list[str]]:
    """Read a CSV or Excel file, returning (rows as dicts, column names)."""
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _read_xlsx(path)
    return _read_csv(path)


def _read_csv(path: Path) -> tuple[list[dict], list[str]]:
    """Read CSV with multi-encoding fallback (utf-8, cp1252, latin-1)."""
    for encoding in _CSV_ENCODINGS:
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []
                rows = []
                for row in reader:
                    coerced = {k: _coerce_value(v) for k, v in row.items()}
                    rows.append(coerced)
                return rows, list(columns)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1, f"Could not decode {path} with utf-8, cp1252, or latin-1"
    )


def _read_xlsx(path: Path) -> tuple[list[dict], list[str]]:
    """Read first sheet of .xlsx with openpyxl (read-only, data-only)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        # Producers like Microsoft Forms can write stale <dimension> metadata that
        # hides populated cells; reset so iteration scans the actual sheet XML.
        ws.reset_dimensions()
        row_iter = ws.iter_rows()
        header_cells = next(row_iter)
        columns = [str(c.value) if c.value is not None else f"col_{i}" for i, c in enumerate(header_cells)]

        rows = []
        for row_cells in row_iter:
            row = dict.fromkeys(columns)
            for col_name, cell in zip(columns, row_cells):
                value = cell.value
                if isinstance(value, datetime):
                    value = value.isoformat()
                row[col_name] = value
            rows.append(row)
        return rows, columns
    finally:
        wb.close()


def _read_text_file(path: Path) -> str:
    """Read a text file with multi-encoding fallback."""
    for encoding in _CSV_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "multi", b"", 0, 1, f"Could not decode {path} with utf-8, cp1252, or latin-1"
    )


def _coerce_value(value: str):
    """Coerce a CSV string value to int, float, or leave as string.

    Empty strings become None.
    """
    if value == "":
        return None
    try:
        int_val = int(value)
        # Avoid converting "07" to 7 — preserve as string if leading zero
        if value != str(int_val):
            return value
        return int_val
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
