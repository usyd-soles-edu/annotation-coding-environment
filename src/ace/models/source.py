"""CRUD operations for source and source_content tables."""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone


def validate_section_heading_spans(
    spans: object,
    content_length: int,
) -> tuple[tuple[int, int], ...] | None:
    """Return normalised half-open spans, or ``None`` when any span is invalid."""
    if not isinstance(spans, Sequence) or isinstance(spans, (str, bytes)):
        return None

    validated: list[tuple[int, int]] = []
    previous_end = 0
    for pair in spans:
        if (
            not isinstance(pair, Sequence)
            or isinstance(pair, (str, bytes))
            or len(pair) != 2
        ):
            return None
        start, end = pair
        if type(start) is not int or type(end) is not int:
            return None
        if start < 0 or start >= end or end > content_length:
            return None
        if validated and start < previous_end:
            return None
        validated.append((start, end))
        previous_end = end
    return tuple(validated)


def decode_section_heading_spans(
    content_text: str,
    section_headings_json: object,
) -> tuple[tuple[int, int], ...]:
    """Decode stored heading spans, failing closed to legacy splitting."""
    if not isinstance(section_headings_json, str):
        return ()
    try:
        parsed = json.loads(section_headings_json)
    except (TypeError, ValueError, RecursionError):
        return ()

    validated = validate_section_heading_spans(parsed, len(content_text))
    return validated if validated is not None else ()


def _encode_section_heading_spans(
    content_text: str,
    spans: Sequence[tuple[int, int]] | None,
) -> str | None:
    if spans is None:
        return None
    validated = validate_section_heading_spans(spans, len(content_text))
    if validated is None:
        raise ValueError(
            "Section heading spans must be ordered, non-overlapping, and in range."
        )
    return json.dumps(validated) if validated else None


def add_source(
    conn: sqlite3.Connection,
    display_id: str,
    content_text: str,
    source_type: str,
    filename: str | None = None,
    source_column: str | None = None,
    metadata: dict | None = None,
    section_heading_spans: Sequence[tuple[int, int]] | None = None,
) -> str:
    source_id = _add_source_no_commit(
        conn,
        display_id,
        content_text,
        source_type,
        filename,
        source_column,
        metadata,
        section_heading_spans,
    )
    conn.commit()
    return source_id


def _add_source_no_commit(
    conn: sqlite3.Connection,
    display_id: str,
    content_text: str,
    source_type: str,
    filename: str | None = None,
    source_column: str | None = None,
    metadata: dict | None = None,
    section_heading_spans: Sequence[tuple[int, int]] | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    source_id = uuid.uuid4().hex
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()
    metadata_json = json.dumps(metadata) if metadata is not None else None
    section_headings_json = _encode_section_heading_spans(
        content_text, section_heading_spans
    )

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM source").fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        "INSERT INTO source (id, display_id, source_type, source_column, filename, metadata_json, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, display_id, source_type, source_column, filename, metadata_json, sort_order, now),
    )
    conn.execute(
        "INSERT INTO source_content "
        "(source_id, content_text, content_hash, section_headings_json) "
        "VALUES (?, ?, ?, ?)",
        (source_id, content_text, content_hash, section_headings_json),
    )
    return source_id


def get_source(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM source WHERE id = ?", (source_id,)).fetchone()


def get_source_content(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM source_content WHERE source_id = ?", (source_id,)).fetchone()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM source ORDER BY sort_order").fetchall()
