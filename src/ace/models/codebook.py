"""CRUD operations for codebook_code table."""

import colorsys
import csv
import hashlib
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
# Codes at position >= 31 (0-indexed by sort_order rank) get a 2-letter chord shortcut.
SINGLE_KEY_LIMIT = 31

_INSERT_CODE_SQL = (
    "INSERT INTO codebook_code "
    "(id, name, colour, sort_order, kind, parent_id, created_at) "
    "VALUES (?, ?, ?, ?, 'code', ?, ?)"
)


# ---------------------------------------------------------------------------
# Colour palette — golden-angle hue spacing with alternating lightness bands
# ---------------------------------------------------------------------------

def _generate_palette(n: int) -> list[tuple[str, str]]:
    golden_ratio = 0.618033988749895
    colours = []
    for i in range(n):
        hue = (i * golden_ratio) % 1.0
        lightness = 0.38 if i % 2 == 0 else 0.62
        saturation = 0.75
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_val = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
        colours.append((hex_val, f"Colour {i + 1}"))
    return colours


COLOUR_PALETTE = _generate_palette(36)


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]

def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    parent_id: str | None = None,
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
        (code_id, name, colour, sort_order, parent_id, now),
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

    Chord shortcuts are derived here, not stored: codes at sort_order rank
    >= SINGLE_KEY_LIMIT get a 2-letter chord assigned by `assign_chord`,
    walking codes in rank order with a growing `taken` set so values are
    deterministic and unique within the snapshot.
    """
    rows = conn.execute(
        "SELECT id, name, colour, sort_order, kind, parent_id "
        "FROM codebook_code WHERE deleted_at IS NULL "
        "ORDER BY sort_order"
    ).fetchall()

    chord_for: dict[str, str] = {}
    rank = 0
    taken: set[str] = set()
    for r in rows:
        if r["kind"] != "code":
            continue
        if rank >= SINGLE_KEY_LIMIT:
            chord = assign_chord(r["name"], taken)
            chord_for[r["id"]] = chord
            taken.add(chord)
        rank += 1

    active_folder_ids = {r["id"] for r in rows if r["kind"] == "folder"}
    by_parent: dict[str | None, list[sqlite3.Row]] = {}
    for r in rows:
        parent_id = r["parent_id"] if r["parent_id"] in active_folder_ids else None
        by_parent.setdefault(parent_id, []).append(r)

    for siblings in by_parent.values():
        siblings.sort(key=lambda r: (0 if r["kind"] == "folder" else 1, r["sort_order"]))

    nodes: dict[str, dict] = {}
    for r in rows:
        parent_id = r["parent_id"] if r["parent_id"] in active_folder_ids else None
        node = {
            "id": r["id"], "name": r["name"], "colour": r["colour"],
            "sort_order": r["sort_order"], "kind": r["kind"],
            "parent_id": parent_id,
            "chord": chord_for.get(r["id"]) if r["kind"] == "code" else None,
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


def reorder_tree(conn: sqlite3.Connection, ids: list[str]) -> None:
    """Reorder a flat list of mixed code+folder ids by sort_order.

    Used by the keyboard folder-reorder gesture (⌥⇧↑/↓), which moves
    folder rows and code rows together. The existing `reorder_codes`
    helper rewrites only a flat code list; this variant updates regardless
    of `kind` so a unified visual order survives subsequent OOB sidebar swaps.
    """
    for i, item_id in enumerate(ids):
        conn.execute(
            "UPDATE codebook_code SET sort_order = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (i, item_id),
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
        "SELECT id, name, colour, kind, parent_id "
        "FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    combined = "".join(
        f"{r['id']}{r['name']}{r['colour']}{r['kind']}{r['parent_id'] or ''}"
        for r in rows
    )
    return hashlib.sha256(combined.encode()).hexdigest()


def _parse_codebook_csv(path: str | Path) -> list[dict]:
    """Parse a codebook CSV file into a list of {name, colour, group_name} dicts.

    Reads 'group' column if present (strips whitespace, preserves casing).
    Ignores 'colour' column — always auto-assigns from palette.
    Raises ValueError if 'name' column is missing.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must have a 'name' column")

        has_group = "group" in (reader.fieldnames or [])
        rows: list[dict] = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            colour = next_colour(len(rows))

            group_name = None
            if has_group:
                g = row.get("group", "").strip()
                if g:
                    group_name = g

            rows.append({"name": name, "colour": colour, "group_name": group_name})
    return rows


def preview_codebook_csv(conn: sqlite3.Connection, path: str | Path) -> list[dict]:
    """Parse a codebook CSV and mark which codes already exist in the project.

    Returns list of {"name", "colour", "group_name", "exists"} dicts. Only
    matches against existing code rows — folder names sharing a string with
    an incoming code are not considered duplicates (kinds are independent).
    """
    rows = _parse_codebook_csv(path)
    existing = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM codebook_code "
            "WHERE deleted_at IS NULL AND kind = 'code'"
        ).fetchall()
    }
    return [
        {**r, "exists": r["name"] in existing}
        for r in rows
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
        r["name"]
        for r in conn.execute(
            "SELECT name FROM codebook_code "
            "WHERE deleted_at IS NULL AND kind = 'code'"
        ).fetchall()
    }
    to_insert = [c for c in codes if c["name"] not in existing]
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
                "(id, name, colour, sort_order, kind, parent_id, created_at) "
                "VALUES (?, ?, ?, ?, 'code', ?, ?)",
                (code_id, code["name"], code["colour"], next_sort,
                 parent_id, now),
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
                "(id, name, colour, sort_order, kind, parent_id, created_at) "
                "VALUES (?, ?, ?, ?, 'code', ?, ?)",
                (code_id, row["name"], row["colour"], next_sort,
                 parent_id, now),
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
               COALESCE(f.name, '') AS group_name
        FROM codebook_code c
        LEFT JOIN codebook_code f
               ON f.id = c.parent_id AND f.kind = 'folder'
        WHERE c.deleted_at IS NULL AND c.kind = 'code'
        ORDER BY c.sort_order
        """
    ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "group"])
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "name": r["name"],
                "group": r["group_name"] or "",
            })
    return len(rows)
