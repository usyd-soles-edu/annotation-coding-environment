"""Migration runner for ACE project files."""

import json
import sqlite3
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Callable

from ace.db.schema import SCHEMA_VERSION
from ace.models.source import validate_section_heading_spans


class NewerSchemaVersionError(ValueError):
    """Raised when a project requires a newer ACE schema."""

    def __init__(self, file_version: int, supported_version: int):
        self.file_version = file_version
        self.supported_version = supported_version
        super().__init__(
            f"Project schema {file_version} is newer than supported schema "
            f"{supported_version}"
        )


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add group_name column to codebook_code."""
    conn.execute("ALTER TABLE codebook_code ADD COLUMN group_name TEXT")


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add deleted_at to codebook_code; replace column-level UNIQUE(name) with partial unique index.

    Wrapped in PRAGMA foreign_keys = OFF because the annotation table has
    code_id REFERENCES codebook_code(id) — dropping codebook_code with FKs on
    would error or cascade.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("""
            CREATE TABLE codebook_code_new (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                colour      TEXT NOT NULL,
                sort_order  INTEGER NOT NULL,
                group_name  TEXT,
                created_at  TEXT NOT NULL,
                deleted_at  TEXT
            );

            INSERT INTO codebook_code_new
                (id, name, colour, sort_order, group_name, created_at, deleted_at)
            SELECT id, name, colour, sort_order, group_name, created_at, NULL
            FROM codebook_code;

            DROP TABLE codebook_code;
            ALTER TABLE codebook_code_new RENAME TO codebook_code;

            CREATE UNIQUE INDEX idx_codebook_code_name_active
                ON codebook_code(name) WHERE deleted_at IS NULL;
        """)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v2→v3 migration: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Replace assignment.status (4-state) with assignment.flagged (binary).

    Only status='flagged' rows become flagged=1; pending / in_progress / complete
    are intentionally collapsed to flagged=0 because the auto-progress feature
    is being removed.

    Defensive: skips if the assignment table doesn't exist (some test fixtures
    construct minimal v1/v2 schemas without it).
    """
    has_assignment = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assignment'"
    ).fetchone()
    if has_assignment is None:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("""
            CREATE TABLE assignment_new (
                id          TEXT PRIMARY KEY,
                source_id   TEXT NOT NULL REFERENCES source(id),
                coder_id    TEXT NOT NULL REFERENCES coder(id),
                flagged     INTEGER NOT NULL DEFAULT 0 CHECK (flagged IN (0, 1)),
                assigned_at TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE(source_id, coder_id)
            );

            INSERT INTO assignment_new
                (id, source_id, coder_id, flagged, assigned_at, updated_at)
            SELECT id, source_id, coder_id,
                   CASE status WHEN 'flagged' THEN 1 ELSE 0 END,
                   assigned_at, updated_at
            FROM assignment;

            DROP TABLE assignment;
            ALTER TABLE assignment_new RENAME TO assignment;

            CREATE INDEX idx_assignment_coder ON assignment(coder_id);
            CREATE INDEX idx_assignment_source ON assignment(source_id);
        """)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v3→v4 migration: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add `chord` column to codebook_code for chord-key shortcuts.

    The column is nullable: the first 31 codes (positions 0-30 by sort_order
    rank) use single-key shortcuts and have NULL chord. Codes at position 31+
    get a 2-letter chord assigned by `services.chord_assignment.assign_chord`.

    Defensive: skips if codebook_code doesn't exist (some test fixtures build
    minimal schemas without it).

    See spec: docs/superpowers/specs/2026-04-29-codebook-chord-keys-design.md
    """
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return

    # Column-existence probe — SQLite has no `ADD COLUMN IF NOT EXISTS`, and a
    # second ALTER raises OperationalError("duplicate column name: chord").
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    if "chord" not in existing_cols:
        conn.execute("ALTER TABLE codebook_code ADD COLUMN chord TEXT")

    # Unique partial index — multiple NULL allowed, but values must be unique
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_codebook_chord
            ON codebook_code(chord) WHERE chord IS NOT NULL AND deleted_at IS NULL
    """)


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """Tighten chord uniqueness index to exclude soft-deleted rows.

    The v5 index `idx_codebook_chord` only excluded NULL chords. This meant a
    soft-deleted code's chord still occupied the unique slot, blocking re-use
    after deletion and causing IntegrityErrors on backfill (since
    `_taken_chords` correctly excludes deleted rows).

    See PR #2 review.
    """
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return
    conn.execute("DROP INDEX IF EXISTS idx_codebook_chord")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_codebook_chord
            ON codebook_code(chord) WHERE chord IS NOT NULL AND deleted_at IS NULL
    """)


def _migrate_v6_to_v7(conn: sqlite3.Connection) -> None:
    """Add kind + parent_id; migrate group_name → folder rows; drop group_name.

    The migration is idempotent at every step:
      • column-existence guards on ALTER TABLE
      • INSERT … WHERE NOT EXISTS for folder rows
      • DROP INDEX IF EXISTS / CREATE UNIQUE INDEX IF NOT EXISTS for index swap

    Includes soft-deleted v6 rows in the group scan so undo can later restore
    them with their original folder context.

    See spec: docs/superpowers/specs/2026-05-01-codebook-redesign-design.md
    """
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return

    cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    now = datetime.now(timezone.utc).isoformat()

    # Step A: add columns if not yet present.
    if "kind" not in cols:
        conn.execute(
            "ALTER TABLE codebook_code "
            "ADD COLUMN kind TEXT NOT NULL DEFAULT 'code' "
            "CHECK (kind IN ('code', 'folder'))"
        )
    if "parent_id" not in cols:
        conn.execute(
            "ALTER TABLE codebook_code "
            "ADD COLUMN parent_id TEXT REFERENCES codebook_code(id) ON DELETE SET NULL"
        )

    # Step B: rebuild the unique-name index as (name, kind) NOCASE so a folder
    # and a code can share a name (per spec §3.5.5) and case collisions ("Themes"
    # vs "themes") are detected.
    conn.execute("DROP INDEX IF EXISTS idx_codebook_code_name_active")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_codebook_code_name_active "
        "ON codebook_code(name COLLATE NOCASE, kind) WHERE deleted_at IS NULL"
    )

    # Step C: migrate group_name → folder rows. Skip if column already gone.
    # Only consider live rows — undo lives in memory, so a soft-deleted v6
    # row would never come back into a phantom folder. Including them just
    # creates empty folder rows that confuse the renderer.
    if "group_name" in cols:
        groups = conn.execute(
            "SELECT DISTINCT group_name FROM codebook_code "
            "WHERE group_name IS NOT NULL AND group_name != '' "
            "AND deleted_at IS NULL"
        ).fetchall()

        # Place folder rows below all existing codes' sort_order so the migration
        # doesn't have to renumber.
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code"
        ).fetchone()[0]

        for offset, row in enumerate(groups, start=1):
            group_name = row[0]
            # Idempotent insert — if this folder already exists from a prior
            # half-completed run, skip it and reuse the existing id below.
            existing = conn.execute(
                "SELECT id FROM codebook_code "
                "WHERE name = ? COLLATE NOCASE AND kind = 'folder' AND deleted_at IS NULL",
                (group_name,),
            ).fetchone()
            if existing:
                folder_id = existing[0]
            else:
                folder_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO codebook_code "
                    "(id, name, colour, sort_order, kind, parent_id, chord, created_at, deleted_at) "
                    "VALUES (?, ?, '', ?, 'folder', NULL, NULL, ?, NULL)",
                    (folder_id, group_name, max_sort + offset, now),
                )
            # Set parent_id on every code (including soft-deleted) with this
            # group_name. kind='code' is enforced because folders we just
            # created have kind='folder'.
            conn.execute(
                "UPDATE codebook_code SET parent_id = ? "
                "WHERE group_name = ? AND kind = 'code' AND parent_id IS NULL",
                (folder_id, group_name),
            )

        # Step D: drop group_name. Python 3.12 bundles SQLite ≥ 3.45 which
        # supports DROP COLUMN.
        conn.execute("ALTER TABLE codebook_code DROP COLUMN group_name")


def _migrate_v7_to_v8(conn: sqlite3.Connection) -> None:
    """Add annotation indexes for coding-page render hot paths."""
    has_annotation = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='annotation'"
    ).fetchone()
    if has_annotation is None:
        return

    conn.execute("DROP INDEX IF EXISTS idx_annotation_source_coder")
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_annotation_coder_source_active
            ON annotation(coder_id, source_id) WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_annotation_coder_code_active
            ON annotation(coder_id, code_id) WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_annotation_source_coder_start_active
            ON annotation(source_id, coder_id, start_offset) WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_annotation_source_coder_code_offsets_active
            ON annotation(source_id, coder_id, code_id, start_offset, end_offset)
            WHERE deleted_at IS NULL;
    """)


def _create_annotation_code_leaf_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS annotation_code_id_must_be_code_insert
        BEFORE INSERT ON annotation
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1 FROM codebook_code
            WHERE id = NEW.code_id AND kind = 'code' AND deleted_at IS NULL
        )
        BEGIN
            SELECT RAISE(ABORT, 'annotation code_id must reference an active code');
        END;

        CREATE TRIGGER IF NOT EXISTS annotation_code_id_must_be_code_update
        BEFORE UPDATE OF code_id ON annotation
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1 FROM codebook_code
            WHERE id = NEW.code_id AND kind = 'code' AND deleted_at IS NULL
        )
        BEGIN
            SELECT RAISE(ABORT, 'annotation code_id must reference an active code');
        END;
    """)


def _migrate_v8_to_v9(conn: sqlite3.Connection) -> None:
    """Allow folders to be nested and prevent annotations on folders."""
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("""
            DROP TRIGGER IF EXISTS annotation_code_id_must_be_code_insert;
            DROP TRIGGER IF EXISTS annotation_code_id_must_be_code_update;
            DROP INDEX IF EXISTS idx_codebook_code_name_active;
            DROP INDEX IF EXISTS idx_codebook_chord;
            DROP INDEX IF EXISTS idx_codebook_parent;

            CREATE TABLE codebook_code_new (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                colour      TEXT NOT NULL,
                sort_order  INTEGER NOT NULL,
                kind        TEXT NOT NULL DEFAULT 'code' CHECK (kind IN ('code', 'folder')),
                parent_id   TEXT REFERENCES codebook_code_new(id) ON DELETE SET NULL,
                chord       TEXT,
                created_at  TEXT NOT NULL,
                deleted_at  TEXT,
                CHECK ((kind = 'code') OR (colour = '' AND chord IS NULL))
            );

            INSERT INTO codebook_code_new
                (id, name, colour, sort_order, kind, parent_id, chord, created_at, deleted_at)
            SELECT id, name, colour, sort_order, kind, parent_id, chord, created_at, deleted_at
            FROM codebook_code;

            DROP TABLE codebook_code;
            ALTER TABLE codebook_code_new RENAME TO codebook_code;

            CREATE UNIQUE INDEX idx_codebook_code_name_active
                ON codebook_code(name COLLATE NOCASE, kind) WHERE deleted_at IS NULL;

            CREATE UNIQUE INDEX idx_codebook_chord
                ON codebook_code(chord) WHERE chord IS NOT NULL AND deleted_at IS NULL;

            CREATE INDEX idx_codebook_parent
                ON codebook_code(parent_id) WHERE deleted_at IS NULL;
        """)
        has_annotation = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='annotation'"
        ).fetchone()
        if has_annotation is not None:
            _create_annotation_code_leaf_triggers(conn)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v8→v9 migration: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v9_to_v10(conn: sqlite3.Connection) -> None:
    """Add read-only imported dictionary definitions to code rows."""
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return

    cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    if "definition" not in cols:
        conn.execute("ALTER TABLE codebook_code ADD COLUMN definition TEXT")


def _migrate_v10_to_v11(conn: sqlite3.Connection) -> None:
    """Add optional section-heading spans to source content."""
    has_source_content = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='source_content'"
    ).fetchone()
    if has_source_content is None:
        return

    cols = {r[1] for r in conn.execute("PRAGMA table_info(source_content)").fetchall()}
    if "section_headings_json" not in cols:
        conn.execute(
            "ALTER TABLE source_content ADD COLUMN section_headings_json TEXT"
        )


def _legacy_heading_candidates(content: str) -> list[tuple[str, int, int]]:
    """Return plausible headings at boundaries used by legacy row imports."""
    first_end = content.find("\n")
    if first_end <= 0:
        return []

    first_heading = content[:first_end]
    if not first_heading.strip() or "\r" in first_heading:
        return []

    candidates = [(first_heading, 0, first_end)]
    line_start = first_end + 1
    while line_start < len(content):
        line_end = content.find("\n", line_start)
        if line_end == -1:
            break
        if (
            line_start >= 2
            and content[line_start - 2 : line_start] == "\n\n"
        ):
            heading = content[line_start:line_end]
            if heading.strip() and "\r" not in heading:
                candidates.append((heading, line_start, line_end))
        line_start = line_end + 1
    return candidates


def _infer_legacy_section_heading_spans(
    contents: Sequence[str],
) -> list[tuple[tuple[int, int], ...]] | None:
    """Infer per-row spans only when boundary headings agree unambiguously."""
    if len(contents) < 2:
        return None

    candidates_by_source = [
        _legacy_heading_candidates(content) for content in contents
    ]
    if any(not candidates for candidates in candidates_by_source):
        return None

    first_heading = candidates_by_source[0][0][0]
    if any(
        candidates[0][0] != first_heading or candidates[0][1] != 0
        for candidates in candidates_by_source
    ):
        return None

    counts_by_source = [
        Counter(heading for heading, _start, _end in candidates)
        for candidates in candidates_by_source
    ]
    common_headings = set(counts_by_source[0])
    for counts in counts_by_source[1:]:
        common_headings.intersection_update(counts)

    # Stable value boilerplate at the same boundary in every row is
    # indistinguishable from a lost heading; cross-row agreement is the
    # strongest evidence retained by the legacy schema.

    # A repeated common boundary token has more than one possible span.
    if any(
        counts[heading] != 1
        for heading in common_headings
        for counts in counts_by_source
    ):
        return None

    ordered_headings = [
        heading
        for heading, _start, _end in candidates_by_source[0]
        if heading in common_headings
    ]
    if len(ordered_headings) < 2 or ordered_headings[0] != first_heading:
        return None

    inferred: list[tuple[tuple[int, int], ...]] = []
    for content, candidates in zip(contents, candidates_by_source):
        source_order = [
            heading
            for heading, _start, _end in candidates
            if heading in common_headings
        ]
        if source_order != ordered_headings:
            return None

        positions = {
            heading: (start, end)
            for heading, start, end in candidates
            if heading in common_headings
        }
        spans = tuple(positions[heading] for heading in ordered_headings)
        for index, (start, end) in enumerate(spans):
            if content[end : end + 1] != "\n":
                return None
            if index == 0:
                if start != 0:
                    return None
            elif content[start - 2 : start] != "\n\n":
                return None

        validated = validate_section_heading_spans(spans, len(content))
        if validated is None or len(validated) != len(ordered_headings):
            return None
        inferred.append(validated)

    return inferred


def _legacy_heading_updates(
    group: Sequence[tuple[str, str]],
) -> list[tuple[str, str]]:
    inferred = _infer_legacy_section_heading_spans(
        [content for _source_id, content in group]
    )
    if inferred is None:
        return []
    return [
        (json.dumps(spans, separators=(",", ":")), source_id)
        for (source_id, _content), spans in zip(group, inferred)
    ]


def _migrate_v11_to_v12(conn: sqlite3.Connection) -> None:
    """Recover high-confidence heading spans from legacy multi-column rows."""
    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if not {"source", "source_content"}.issubset(table_names):
        return

    source_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(source)")
    }
    content_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(source_content)")
    }
    if not {
        "id",
        "source_type",
        "filename",
        "sort_order",
    }.issubset(source_columns) or not {
        "source_id",
        "content_text",
        "section_headings_json",
    }.issubset(content_columns):
        return

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.source_type,
            s.filename,
            s.sort_order,
            sc.source_id,
            sc.content_text,
            sc.section_headings_json
        FROM source AS s
        LEFT JOIN source_content AS sc ON sc.source_id = s.id
        ORDER BY s.sort_order, s.id
        """
    )

    updates: list[tuple[str, str]] = []
    group: list[tuple[str, str]] = []
    group_filename: str | None = None
    previous_sort_order: int | None = None

    for (
        source_id,
        source_type,
        filename,
        sort_order,
        content_source_id,
        content,
        headings_json,
    ) in rows:
        eligible = (
            isinstance(source_id, str)
            and source_type == "row"
            and isinstance(filename, str)
            and bool(filename.strip())
            and type(sort_order) is int
            and content_source_id is not None
            and isinstance(content, str)
            and headings_json is None
        )
        starts_new_group = (
            eligible
            and bool(group)
            and (
                filename != group_filename
                or previous_sort_order is None
                or sort_order != previous_sort_order + 1
            )
        )
        if group and (not eligible or starts_new_group):
            updates.extend(_legacy_heading_updates(group))
            group = []

        if not eligible:
            group_filename = None
            previous_sort_order = None
            continue

        if not group:
            group_filename = filename
        group.append((source_id, content))
        previous_sort_order = sort_order

    if group:
        updates.extend(_legacy_heading_updates(group))

    conn.executemany(
        """
        UPDATE source_content
        SET section_headings_json = ?
        WHERE source_id = ? AND section_headings_json IS NULL
        """,
        updates,
    )


# Registry of migration functions keyed by target version.
# Each function takes a connection and migrates from version (key - 1) to key.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_v1_to_v2,
    3: _migrate_v2_to_v3,
    4: _migrate_v3_to_v4,
    5: _migrate_v4_to_v5,
    6: _migrate_v5_to_v6,
    7: _migrate_v6_to_v7,
    8: _migrate_v7_to_v8,
    9: _migrate_v8_to_v9,
    10: _migrate_v9_to_v10,
    11: _migrate_v10_to_v11,
    12: _migrate_v11_to_v12,
}


def check_and_migrate(conn: sqlite3.Connection) -> int:
    """Check user_version and apply sequential migrations if needed.

    Returns the current schema version after any migrations.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise NewerSchemaVersionError(current, SCHEMA_VERSION)

    while current < SCHEMA_VERSION:
        next_version = current + 1
        migrate_fn = MIGRATIONS.get(next_version)
        if migrate_fn is None:
            raise RuntimeError(
                f"No migration found for version {current} -> {next_version}"
            )
        migrate_fn(conn)
        conn.execute(f"PRAGMA user_version = {next_version}")
        conn.commit()
        current = next_version

    return current
