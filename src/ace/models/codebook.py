"""CRUD operations for codebook_code table."""

import csv
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.models.codebook_invariants import (
    InvariantError,
    assert_no_cycle,
    assert_parent_is_folder_or_root,
)
from ace.services.chord_assignment import assign_chord

# Single-key shortcut slots: 10 digits (1-9, 0) + a-p minus n (15) +
# r-y minus v and x (6) = 31. Reserved keys: q, x, z, n, v.
# Codes at position >= 31 in flattened tree order get a 2-letter chord shortcut.
SINGLE_KEY_LIMIT = 31

_INSERT_CODE_SQL = (
    "INSERT INTO codebook_code "
    "(id, name, colour, sort_order, kind, parent_id, definition, created_at) "
    "VALUES (?, ?, ?, ?, 'code', ?, ?, ?)"
)

CODEBOOK_COLUMN_ALIASES = {
    "name": ("name", "code", "code_name", "code name", "code label", "label", "category"),
    "group": ("group", "folder", "parent", "theme"),
    "definition": (
        "definition", "description", "dictionary", "meaning", "notes",
        "dictionary definition", "code definition",
    ),
}


# ---------------------------------------------------------------------------
# Colour palette — curated for visible 4 px code stripes and translucent highlights
# ---------------------------------------------------------------------------

_COLOUR_PALETTE_PATH = Path(__file__).resolve().parents[1] / "static" / "code_palette.json"


def _load_colour_palette() -> list[tuple[str, str]]:
    raw = json.loads(_COLOUR_PALETTE_PATH.read_text(encoding="utf-8"))
    return [(item["hex"], item["label"]) for item in raw]


COLOUR_PALETTE = _load_colour_palette()


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]


def code_name(conn: sqlite3.Connection, code_id: str) -> str:
    """Return the code's display name, or '(deleted code)' if it no longer exists.

    Shared by status-message rendering (api.py apply routes) and the undo
    description helpers (services/undo.py).
    """
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    return row["name"] if row else "(deleted code)"


def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    parent_id: str | None = None,
    definition: str | None = None,
) -> str:
    assert_parent_is_folder_or_root(conn, parent_id)
    now = datetime.now(timezone.utc).isoformat()
    code_id = uuid.uuid4().hex

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        _INSERT_CODE_SQL,
        (code_id, name, colour, sort_order, parent_id, definition, now),
    )
    conn.commit()
    return code_id


def _add_folder_no_commit(
    conn: sqlite3.Connection,
    name: str,
    parent_id: str | None = None,
) -> str:
    """Folder-create primitive used by transactional composites.

    Same shape as `add_folder` but the caller owns commit/rollback. Used by
    Task 9's indent-promote route which wraps folder creation + two moves in
    a single BEGIN IMMEDIATE / COMMIT.
    """
    assert_parent_is_folder_or_root(conn, parent_id)
    now = datetime.now(timezone.utc).isoformat()
    folder_id = uuid.uuid4().hex
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO codebook_code "
        "(id, name, colour, sort_order, kind, parent_id, created_at) "
        "VALUES (?, ?, '', ?, 'folder', ?, ?)",
        (folder_id, name, max_order + 1, parent_id, now),
    )
    return folder_id


def add_folder(
    conn: sqlite3.Connection,
    name: str,
    parent_id: str | None = None,
) -> str:
    """Create a folder row. Returns the new folder id."""
    folder_id = _add_folder_no_commit(conn, name, parent_id=parent_id)
    conn.commit()
    return folder_id


def list_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM codebook_code WHERE deleted_at IS NULL ORDER BY sort_order"
    ).fetchall()


def list_codes_with_tree(conn: sqlite3.Connection) -> list[dict]:
    """Return rows in DFS-tree order.

    Each folder row carries `children`, `child_count`, and `child_ids` for the
    recursive renderer. Codes are leaves. Orphans are surfaced at root.

    Chord shortcuts are derived here, not stored: codes at flattened tree rank
    >= SINGLE_KEY_LIMIT get a 2-letter chord assigned by `assign_chord`,
    walking visible codes in rank order with a growing `taken` set so values are
    deterministic and unique within the snapshot.
    """
    rows = conn.execute(
        "SELECT id, name, colour, sort_order, kind, parent_id, definition "
        "FROM codebook_code WHERE deleted_at IS NULL "
        "ORDER BY sort_order"
    ).fetchall()

    active_folder_ids = {r["id"] for r in rows if r["kind"] == "folder"}
    by_parent: dict[str | None, list[sqlite3.Row]] = {}
    for r in rows:
        parent_id = r["parent_id"] if r["parent_id"] in active_folder_ids else None
        by_parent.setdefault(parent_id, []).append(r)

    for siblings in by_parent.values():
        siblings.sort(key=lambda r: r["sort_order"])

    nodes: dict[str, dict] = {}
    for r in rows:
        parent_id = r["parent_id"] if r["parent_id"] in active_folder_ids else None
        node = {
            "id": r["id"], "name": r["name"], "colour": r["colour"],
            "sort_order": r["sort_order"], "kind": r["kind"],
            "parent_id": parent_id,
            "definition": r["definition"] if r["kind"] == "code" else None,
            "chord": None,
            "level": 1,
            "children": [],
        }
        if r["kind"] == "folder":
            child_rows = by_parent.get(r["id"], [])
            node["colour"] = ""
            node["child_count"] = len(child_rows)
            node["child_ids"] = [c["id"] for c in child_rows]
        nodes[r["id"]] = node

    out: list[dict] = []
    visited: set[str] = set()

    def visit(row: sqlite3.Row, level: int) -> dict | None:
        row_id = row["id"]
        if row_id in visited:
            return None
        visited.add(row_id)
        node = nodes[row_id]
        node["level"] = level
        out.append(node)
        if row["kind"] == "folder":
            children = []
            for child in by_parent.get(row_id, []):
                child_node = visit(child, level + 1)
                if child_node is not None:
                    children.append(child_node)
            node["children"] = children
        return node

    roots: list[dict] = []
    for row in by_parent.get(None, []):
        root_node = visit(row, 1)
        if root_node is not None:
            roots.append(root_node)

    # Defensive: if existing data somehow contains a cycle or non-rooted chain,
    # expose any unvisited rows at root rather than hiding them.
    for row in rows:
        if row["id"] in visited:
            continue
        nodes[row["id"]]["parent_id"] = None
        root_node = visit(row, 1)
        if root_node is not None:
            roots.append(root_node)

    rank = 0
    taken: set[str] = set()
    for node in out:
        if node["kind"] != "code":
            continue
        if rank >= SINGLE_KEY_LIMIT:
            chord = assign_chord(node["name"], taken)
            node["chord"] = chord
            taken.add(chord)
        rank += 1

    # Keep the top-level list flat for existing callers/tests, but attach the
    # root list to the first item so templates can recurse without rebuilding.
    if out:
        out[0]["root_nodes"] = roots
    return out


def update_code(
    conn: sqlite3.Connection,
    code_id: str,
    name: str | None = None,
    colour: str | None = None,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if colour is not None:
        updates.append("colour = ?")
        params.append(colour)
    if not updates:
        return
    params.append(code_id)
    conn.execute(
        f"UPDATE codebook_code SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


def reorder_codes(conn: sqlite3.Connection, code_ids: list[str]) -> None:
    for i, code_id in enumerate(code_ids):
        conn.execute(
            "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
            (i, code_id),
        )
    conn.commit()


def _move_code_to_parent_no_commit(
    conn: sqlite3.Connection,
    code_id: str,
    new_parent_id: str | None,
) -> None:
    """Move primitive used by transactional composites.

    Same invariant checks and write as `move_code_to_parent` but the caller
    owns commit/rollback. Used by Task 9's indent-promote route which wraps
    folder creation + two moves in a single BEGIN IMMEDIATE / COMMIT.
    """
    assert_parent_is_folder_or_root(conn, new_parent_id)
    assert_no_cycle(conn, code_id, new_parent_id)

    # Place at end of the destination scope.
    max_in_scope = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code "
        "WHERE deleted_at IS NULL "
        "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
        (new_parent_id, new_parent_id),
    ).fetchone()[0]

    conn.execute(
        "UPDATE codebook_code SET parent_id = ?, sort_order = ? WHERE id = ?",
        (new_parent_id, max_in_scope + 1, code_id),
    )


def move_code_to_parent(
    conn: sqlite3.Connection,
    code_id: str,
    new_parent_id: str | None,
) -> None:
    """Move a codebook item into a folder, or to root.

    Raises InvariantError on illegal moves (under code, self, descendant).
    Recomputes `sort_order` to place the row at the end of the
    destination scope. Atomic.
    """
    _move_code_to_parent_no_commit(conn, code_id, new_parent_id)
    conn.commit()


def convert_code_to_folder(conn: sqlite3.Connection, code_id: str) -> dict:
    """Convert a code row into a folder.

    If the code has annotation rows, create a same-named child code and move
    those annotations to the child so folders never become annotation targets.
    Returns metadata needed for undo.
    """
    row = conn.execute(
        "SELECT id, name, colour, sort_order, kind, parent_id, chord "
        "FROM codebook_code WHERE id = ? AND deleted_at IS NULL",
        (code_id,),
    ).fetchone()
    if row is None:
        raise ValueError("code not found")
    if row["kind"] != "code":
        raise InvariantError("only codes can be converted to folders")

    annotation_rows = conn.execute(
        "SELECT id FROM annotation WHERE code_id = ?",
        (code_id,),
    ).fetchall()
    annotation_ids = [r["id"] for r in annotation_rows]
    child_code_id = uuid.uuid4().hex if annotation_ids else None
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE codebook_code "
            "SET kind = 'folder', colour = '', chord = NULL "
            "WHERE id = ?",
            (code_id,),
        )
        if child_code_id is not None:
            conn.execute(
                "INSERT INTO codebook_code "
                "(id, name, colour, sort_order, kind, parent_id, chord, created_at) "
                "VALUES (?, ?, ?, ?, 'code', ?, ?, ?)",
                (
                    child_code_id,
                    row["name"],
                    row["colour"],
                    row["sort_order"] + 1,
                    code_id,
                    row["chord"],
                    now,
                ),
            )
            placeholders = ",".join("?" * len(annotation_ids))
            conn.execute(
                f"UPDATE annotation SET code_id = ? WHERE id IN ({placeholders})",
                [child_code_id, *annotation_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "code_id": code_id,
        "name": row["name"],
        "prev_colour": row["colour"],
        "prev_chord": row["chord"],
        "child_code_id": child_code_id,
        "annotation_ids": annotation_ids,
    }


def delete_code(
    conn: sqlite3.Connection, code_id: str,
) -> tuple[list[str], list[str]]:
    """Soft-delete a code or folder.

    For a code: soft-deletes referencing annotations.
    For a folder: lifts each child's parent_id to NULL (in one txn), then
    soft-deletes the folder. No annotation cascade for folders since folders
    aren't referenced by annotations.

    Returns (affected_annotation_ids, affected_child_ids). Either can be empty.
    Caller passes both to restore_code() to undo.
    """
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT kind FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    if row is None:
        return [], []

    affected_annotations: list[str] = []
    affected_children: list[str] = []

    try:
        if row["kind"] == "folder":
            children = conn.execute(
                "SELECT id FROM codebook_code "
                "WHERE parent_id = ? AND deleted_at IS NULL",
                (code_id,),
            ).fetchall()
            affected_children = [r["id"] for r in children]
            if affected_children:
                conn.execute(
                    "UPDATE codebook_code SET parent_id = NULL "
                    "WHERE parent_id = ? AND deleted_at IS NULL",
                    (code_id,),
                )
        else:
            ann_rows = conn.execute(
                "SELECT id FROM annotation WHERE code_id = ? AND deleted_at IS NULL",
                (code_id,),
            ).fetchall()
            affected_annotations = [r["id"] for r in ann_rows]
            if affected_annotations:
                conn.execute(
                    "UPDATE annotation SET deleted_at = ? "
                    "WHERE code_id = ? AND deleted_at IS NULL",
                    (now, code_id),
                )

        conn.execute(
            "UPDATE codebook_code SET deleted_at = ? WHERE id = ?",
            (now, code_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return affected_annotations, affected_children


def restore_code(
    conn: sqlite3.Connection,
    code_id: str,
    annotation_ids: list[str],
    children_lifted_ids: list[str] | None = None,
) -> None:
    """Inverse of delete_code.

    Restores the code/folder row, re-links any children that were lifted to
    root by the folder cascade, and un-deletes the listed annotations. Atomic.
    """
    try:
        conn.execute(
            "UPDATE codebook_code SET deleted_at = NULL WHERE id = ?",
            (code_id,),
        )
        for cid in children_lifted_ids or []:
            conn.execute(
                "UPDATE codebook_code SET parent_id = ? WHERE id = ?",
                (code_id, cid),
            )
        for ann_id in annotation_ids:
            conn.execute(
                "UPDATE annotation SET deleted_at = NULL WHERE id = ?",
                (ann_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def compute_codebook_hash(conn: sqlite3.Connection) -> str:
    """Hash the codebook structure for agreement-cache invalidation.

    Includes (id, name, colour, kind, parent_id_or_'') — `sort_order` is
    deliberately excluded so reorders don't churn agreement caches. Folder
    rename / move / delete still invalidates because folder rows are part of
    the hash and codes' parent_id changes when their parent moves.
    """
    rows = conn.execute(
        "SELECT id, name, colour, kind, parent_id, definition "
        "FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    combined = "".join(
        f"{r['id']}{r['name']}{r['colour']}{r['kind']}{r['parent_id'] or ''}{r['definition'] or ''}"
        for r in rows
    )
    return hashlib.sha256(combined.encode()).hexdigest()


def _normalise_column_name(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())


def _detect_codebook_columns(fieldnames: list[str]) -> dict[str, str | None]:
    by_normalised = {_normalise_column_name(name): name for name in fieldnames}
    detected: dict[str, str | None] = {}
    for role, aliases in CODEBOOK_COLUMN_ALIASES.items():
        detected[role] = None
        for alias in aliases:
            column = by_normalised.get(_normalise_column_name(alias))
            if column is not None:
                detected[role] = column
                break
    return detected


def inspect_codebook_csv(path: str | Path, sample_limit: int = 20) -> dict:
    """Return codebook CSV headers, detected mappings, and sample rows."""
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        sample_rows = []
        for index, row in enumerate(reader):
            if index >= sample_limit:
                break
            sample_rows.append({name: row.get(name, "") for name in fieldnames})
    return {
        "columns": fieldnames,
        "detected": _detect_codebook_columns(fieldnames),
        "sample_rows": sample_rows,
    }


def _resolve_codebook_csv_columns(
    fieldnames: list[str],
    name_column: str | None = None,
    group_column: str | None = None,
    definition_column: str | None = None,
) -> tuple[str, str | None, str | None]:
    detected = _detect_codebook_columns(fieldnames)
    resolved_name = name_column or detected.get("name")
    resolved_group = group_column if group_column is not None else detected.get("group")
    resolved_definition = (
        definition_column
        if definition_column is not None
        else detected.get("definition")
    )

    if not resolved_name or resolved_name not in fieldnames:
        raise ValueError("Choose a code-name column to import")
    if resolved_group == "":
        resolved_group = None
    if resolved_definition == "":
        resolved_definition = None
    if resolved_group is not None and resolved_group not in fieldnames:
        raise ValueError("Selected folder column was not found in the CSV")
    if resolved_definition is not None and resolved_definition not in fieldnames:
        raise ValueError("Selected definition column was not found in the CSV")
    return resolved_name, resolved_group, resolved_definition


def _normalise_codebook_csv_row(
    row: dict,
    *,
    name_column: str,
    group_column: str | None,
    definition_column: str | None,
    colour: str,
) -> dict:
    name = row.get(name_column, "").strip()

    group_name = None
    if group_column:
        g = row.get(group_column, "").strip()
        if g:
            group_name = g

    definition = None
    if definition_column:
        d = row.get(definition_column, "").strip()
        if d:
            definition = d

    return {
        "name": name,
        "colour": colour,
        "group_name": group_name,
        "definition": definition,
    }


def _parse_codebook_csv(
    path: str | Path,
    name_column: str | None = None,
    group_column: str | None = None,
    definition_column: str | None = None,
) -> list[dict]:
    """Parse a codebook CSV file into code dicts using selected columns.

    Auto-detects columns when a role is not supplied. The code-name column is
    required after detection. Group/folder and definition columns are optional.
    Ignores colour columns — ACE always auto-assigns from the palette.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if reader.fieldnames is None:
            raise ValueError("Choose a code-name column to import")
        name_column, group_column, definition_column = _resolve_codebook_csv_columns(
            fieldnames,
            name_column=name_column,
            group_column=group_column,
            definition_column=definition_column,
        )

        rows: list[dict] = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get(name_column, "").strip()
            name_key = name.lower()
            if not name or name_key in seen_names:
                continue
            seen_names.add(name_key)

            colour = next_colour(len(rows))
            rows.append(_normalise_codebook_csv_row(
                row,
                name_column=name_column,
                group_column=group_column,
                definition_column=definition_column,
                colour=colour,
            ))
    return rows


def preview_codebook_csv_ledger(
    conn: sqlite3.Connection,
    path: str | Path,
    name_column: str | None = None,
    group_column: str | None = None,
    definition_column: str | None = None,
) -> dict:
    """Return row-level preview metadata for the codebook import dialog."""
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if reader.fieldnames is None:
            raise ValueError("Choose a code-name column to import")
        name_column, group_column, definition_column = _resolve_codebook_csv_columns(
            fieldnames,
            name_column=name_column,
            group_column=group_column,
            definition_column=definition_column,
        )

        existing = {
            r["name"].lower()
            for r in conn.execute(
                "SELECT name FROM codebook_code "
                "WHERE deleted_at IS NULL AND kind = 'code'"
            ).fetchall()
        }
        seen_names: set[str] = set()
        rows: list[dict] = []
        importable: list[dict] = []
        accepted_count = 0
        row_count = 0

        for csv_index, row in enumerate(reader, start=2):
            row_count += 1
            name = row.get(name_column, "").strip()
            name_key = name.lower()
            base = _normalise_codebook_csv_row(
                row,
                name_column=name_column,
                group_column=group_column,
                definition_column=definition_column,
                colour="",
            )

            if not name:
                rows.append({
                    **base,
                    "row_number": csv_index,
                    "status": "skipped",
                    "reason": "missing code name",
                    "exists": False,
                })
                continue

            if name_key in seen_names:
                rows.append({
                    **base,
                    "row_number": csv_index,
                    "status": "skipped",
                    "reason": "duplicate in this file",
                    "exists": False,
                })
                continue
            seen_names.add(name_key)

            colour = next_colour(accepted_count)
            accepted_count += 1
            item = {
                **_normalise_codebook_csv_row(
                    row,
                    name_column=name_column,
                    group_column=group_column,
                    definition_column=definition_column,
                    colour=colour,
                ),
                "row_number": csv_index,
                "status": "existing" if name_key in existing else "new",
                "reason": "already in this project" if name_key in existing else "",
                "exists": name_key in existing,
            }
            rows.append(item)
            if not item["exists"]:
                importable.append({
                    "name": item["name"],
                    "colour": item["colour"],
                    "group_name": item.get("group_name"),
                    "definition": item.get("definition"),
                })

    counts = {
        "rows": row_count,
        "new": sum(1 for row in rows if row["status"] == "new"),
        "existing": sum(1 for row in rows if row["status"] == "existing"),
        "skipped": sum(1 for row in rows if row["status"] == "skipped"),
    }
    return {
        "fieldnames": fieldnames,
        "rows": rows,
        "importable": importable,
        "counts": counts,
        "row_count": row_count,
    }


def preview_codebook_csv(
    conn: sqlite3.Connection,
    path: str | Path,
    name_column: str | None = None,
    group_column: str | None = None,
    definition_column: str | None = None,
) -> list[dict]:
    """Parse a codebook CSV and mark which codes already exist in the project.

    Returns list of {"name", "colour", "group_name", "exists"} dicts. Only
    matches against existing code rows — folder names sharing a string with
    an incoming code are not considered duplicates (kinds are independent).
    """
    ledger = preview_codebook_csv_ledger(
        conn,
        path,
        name_column=name_column,
        group_column=group_column,
        definition_column=definition_column,
    )
    return [
        {
            "name": row["name"],
            "colour": row["colour"],
            "group_name": row.get("group_name"),
            "definition": row.get("definition"),
            "exists": row["exists"],
        }
        for row in ledger["rows"]
        if row["status"] in {"new", "existing"}
    ]


def _ensure_folder(conn: sqlite3.Connection, name: str) -> str:
    """Return folder id, creating the folder if absent.

    Match is NOCASE so we line up with the schema's
    `idx_codebook_code_name_active` partial unique index — otherwise a CSV
    re-import that differs only in casing would attempt to create a duplicate
    folder and crash on the unique-name constraint.
    """
    row = conn.execute(
        "SELECT id FROM codebook_code "
        "WHERE name = ? COLLATE NOCASE "
        "AND kind = 'folder' AND deleted_at IS NULL",
        (name,),
    ).fetchone()
    if row:
        return row["id"]
    return _add_folder_no_commit(conn, name)


def _ensure_folder_at(
    conn: sqlite3.Connection, name: str, sort_order: int
) -> tuple[str, bool]:
    """Cursor variant of `_ensure_folder` for CSV import loops.

    Returns ``(folder_id, created)``. When ``created`` is True the caller
    should advance its sort_order cursor; ``_add_folder_no_commit`` would
    pick its own sort_order from `MAX(sort_order)+1`, which collides with
    the cursor's next slot once the loop's first code insert runs.
    """
    row = conn.execute(
        "SELECT id FROM codebook_code "
        "WHERE name = ? COLLATE NOCASE "
        "AND kind = 'folder' AND deleted_at IS NULL",
        (name,),
    ).fetchone()
    if row:
        return row["id"], False
    now = datetime.now(timezone.utc).isoformat()
    folder_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO codebook_code "
        "(id, name, colour, sort_order, kind, parent_id, created_at) "
        "VALUES (?, ?, '', ?, 'folder', NULL, ?)",
        (folder_id, name, sort_order, now),
    )
    return folder_id, True


def import_selected_codes(conn: sqlite3.Connection, codes: list[dict]) -> list[str]:
    """Import a pre-filtered list of codes into the codebook.

    Each dict must have 'name' and 'colour' keys; optional 'group_name'
    becomes the parent folder (created if absent).
    Skips codes whose name already exists (safety net).
    All inserts in a single transaction with rollback on failure.
    Returns the list of inserted code IDs (in the order they were inserted).
    """
    if not codes:
        return []

    existing = {
        r["name"].lower()
        for r in conn.execute(
            "SELECT name FROM codebook_code "
            "WHERE deleted_at IS NULL AND kind = 'code'"
        ).fetchall()
    }
    to_insert = [c for c in codes if c["name"].lower() not in existing]
    if not to_insert:
        return []

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()

    inserted_ids: list[str] = []
    try:
        # Single monotonically-increasing cursor — every inserted row
        # (folder OR code) takes one slot. Advancing only on code inserts
        # would let a freshly-created folder claim the next code's slot
        # via _add_folder_no_commit's MAX+1 lookup.
        next_sort = max_order + 1
        for code in to_insert:
            parent_id = None
            gn = code.get("group_name")
            if gn:
                parent_id, created = _ensure_folder_at(conn, gn, next_sort)
                if created:
                    next_sort += 1
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code "
                "(id, name, colour, sort_order, kind, parent_id, definition, created_at) "
                "VALUES (?, ?, ?, ?, 'code', ?, ?, ?)",
                (code_id, code["name"], code["colour"], next_sort,
                 parent_id, code.get("definition") or None, now),
            )
            next_sort += 1
            inserted_ids.append(code_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return inserted_ids


def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    rows_to_insert = _parse_codebook_csv(path)

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    try:
        # See `import_selected_codes` for the cursor rationale: folders
        # created mid-loop must take a slot from the same counter or
        # they collide with the next code's sort_order.
        next_sort = max_order + 1
        for row in rows_to_insert:
            parent_id = None
            gn = row.get("group_name")
            if gn:
                parent_id, created = _ensure_folder_at(conn, gn, next_sort)
                if created:
                    next_sort += 1
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code "
                "(id, name, colour, sort_order, kind, parent_id, definition, created_at) "
                "VALUES (?, ?, ?, ?, 'code', ?, ?, ?)",
                (code_id, row["name"], row["colour"], next_sort,
                 parent_id, row.get("definition") or None, now),
            )
            next_sort += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)


def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    rows = conn.execute(
        """
        SELECT c.name AS name,
               COALESCE(f.name, '') AS group_name,
               COALESCE(c.definition, '') AS definition
        FROM codebook_code c
        LEFT JOIN codebook_code f
               ON f.id = c.parent_id AND f.kind = 'folder'
        WHERE c.deleted_at IS NULL AND c.kind = 'code'
        ORDER BY c.sort_order
        """
    ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "group", "definition"])
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "name": r["name"],
                "group": r["group_name"] or "",
                "definition": r["definition"] or "",
            })
    return len(rows)
