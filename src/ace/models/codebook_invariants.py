"""Guard functions for codebook tree shape.

Called from model-layer write paths to fail fast with clear messages.
The schema also enforces (kind IN ('code','folder')) via CHECK; these
guards add the relational rules the schema can't express.
"""

import sqlite3


class InvariantError(ValueError):
    """Raised when a write would violate a codebook tree invariant."""


def assert_parent_is_folder_or_root(
    conn: sqlite3.Connection, parent_id: str | None
) -> None:
    """Allow None (root) or a row with kind='folder'. Reject anything else."""
    if parent_id is None:
        return
    row = conn.execute(
        "SELECT kind FROM codebook_code WHERE id = ? AND deleted_at IS NULL",
        (parent_id,),
    ).fetchone()
    if row is None:
        raise InvariantError(f"parent_id {parent_id!r} does not exist")
    if row[0] != "folder":
        raise InvariantError("parent must be a folder")


def assert_no_cycle(
    conn: sqlite3.Connection, item_id: str, new_parent_id: str | None
) -> None:
    """Reject moving a folder under itself or one of its descendants."""
    if new_parent_id is None:
        return
    if item_id == new_parent_id:
        raise InvariantError("folder cannot contain itself")

    row = conn.execute(
        "SELECT kind FROM codebook_code WHERE id = ? AND deleted_at IS NULL",
        (item_id,),
    ).fetchone()
    if row is None or row[0] != "folder":
        return

    ancestor_id = new_parent_id
    seen: set[str] = set()
    while ancestor_id is not None:
        if ancestor_id == item_id:
            raise InvariantError("folder cannot move inside its own child")
        if ancestor_id in seen:
            raise InvariantError("folder cycle detected")
        seen.add(ancestor_id)
        parent = conn.execute(
            "SELECT parent_id FROM codebook_code "
            "WHERE id = ? AND deleted_at IS NULL",
            (ancestor_id,),
        ).fetchone()
        if parent is None:
            return
        ancestor_id = parent[0]
