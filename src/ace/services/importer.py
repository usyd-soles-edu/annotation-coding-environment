"""Import sources from CSV/Excel files and text file folders."""

import csv
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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
        content_text = (
            _combine_text_columns(row, text_columns) if has_selected_text else ""
        )

        candidates.append(
            _SourceCandidate(
                display_id=display_id,
                content_text=content_text,
                source_type="row",
                filename=path.name,
                source_column=None,
                metadata=metadata,
                empty=not has_selected_text,
            )
        )

    return _insert_candidates(conn, candidates, empty_skipped=empty_skipped)


def _row_has_selected_text(row: dict, text_columns: list[str]) -> bool:
    return any(
        value is not None and str(value).strip() != ""
        for value in (row.get(col) for col in text_columns)
    )


def _combine_text_columns(row: dict, text_columns: list[str]) -> str:
    if len(text_columns) == 1:
        value = row[text_columns[0]]
        return "" if value is None else str(value)

    sections = []
    for col in text_columns:
        value = row[col]
        text = "" if value is None else str(value)
        sections.append(f"{col}\n{text}")
    return "\n\n".join(sections)


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
