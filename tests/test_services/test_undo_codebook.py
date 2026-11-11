"""Undo handlers for the new codebook folder operations."""
import pytest

from ace.db.connection import open_project, create_project
from ace.models.codebook import (
    add_code, add_folder, move_code_to_parent, delete_code, list_codes,
    import_selected_codes,
)
from ace.services.undo import UndoManager


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.ace"
    create_project(str(db), "Test")
    return open_project(str(db))


def test_undo_create_folder_soft_deletes_it(conn):
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    mgr.record_create_folder(fid)

    assert mgr.undo(conn) is not None
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is not None


def test_undo_grouped_import_removes_its_new_folder(conn):
    mgr = UndoManager()
    imported = import_selected_codes(
        conn, [{"name": "Happy", "colour": "#FF0000", "group_name": "Emotions"}]
    )
    mgr.record_codebook_import(imported.code_ids, imported.created_folder_ids)

    mgr.undo(conn)

    assert list_codes(conn) == []


def _active_codebook(conn):
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT id, name, kind, parent_id, sort_order FROM codebook_code "
            "WHERE deleted_at IS NULL ORDER BY sort_order, id"
        )
    ]


def test_grouped_import_undo_keeps_reused_folders_and_redo_restores_order(conn):
    mgr = UndoManager()
    existing_folder = add_folder(conn, "Existing")
    before = _active_codebook(conn)
    imported = import_selected_codes(conn, [
        {"name": "First", "colour": "#FF0000", "group_name": "Existing"},
        {"name": "Second", "colour": "#00FF00", "group_name": "New"},
        {"name": "Third", "colour": "#0000FF", "group_name": "New"},
    ])
    assert len(imported.created_folder_ids) == 1
    assert imported.created_folder_ids != [existing_folder]
    after = _active_codebook(conn)
    mgr.record_codebook_import(imported.code_ids, imported.created_folder_ids)

    mgr.undo(conn)
    assert _active_codebook(conn) == before
    mgr.redo(conn)
    assert _active_codebook(conn) == after


def test_grouped_import_undo_and_redo_roll_back_on_mid_operation_error(
    conn, monkeypatch
):
    from ace.models import codebook

    mgr = UndoManager()
    imported = import_selected_codes(conn, [
        {"name": "First", "colour": "#FF0000", "group_name": "New"},
        {"name": "Second", "colour": "#00FF00", "group_name": "New"},
    ])
    mgr.record_codebook_import(imported.code_ids, imported.created_folder_ids)
    active_after_import = _active_codebook(conn)

    original_delete = codebook._delete_code_no_commit
    delete_calls = 0

    def fail_second_delete(db, code_id):
        nonlocal delete_calls
        delete_calls += 1
        if delete_calls == 2:
            raise RuntimeError("simulated undo failure")
        return original_delete(db, code_id)

    with monkeypatch.context() as patcher:
        patcher.setattr(codebook, "_delete_code_no_commit", fail_second_delete)
        with pytest.raises(RuntimeError, match="simulated undo failure"):
            mgr.undo(conn)
    assert _active_codebook(conn) == active_after_import
    assert mgr.can_undo()

    mgr.undo(conn)
    active_after_undo = _active_codebook(conn)
    original_restore = codebook._restore_code_no_commit
    restore_calls = 0

    def fail_second_restore(db, code_id, annotation_ids):
        nonlocal restore_calls
        restore_calls += 1
        if restore_calls == 2:
            raise RuntimeError("simulated redo failure")
        return original_restore(db, code_id, annotation_ids)

    with monkeypatch.context() as patcher:
        patcher.setattr(codebook, "_restore_code_no_commit", fail_second_restore)
        with pytest.raises(RuntimeError, match="simulated redo failure"):
            mgr.redo(conn)
    assert _active_codebook(conn) == active_after_undo
    assert mgr.can_redo()

    mgr.redo(conn)
    assert _active_codebook(conn) == active_after_import


def _snapshot_scope(conn, parent_id):
    """List of (id, sort_order) for everything in a scope. Helper for undo tests."""
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL "
        "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
        (parent_id, parent_id),
    ).fetchall()
    return [(r["id"], r["sort_order"]) for r in rows]


def test_undo_move_parent_restores_sibling_orderings(conn):
    """After move-and-undo, both source and dest scopes are sort-order-byte-identical
    to the pre-move snapshot."""
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    cid_a = add_code(conn, "Identity", "#D55E00")
    cid_b = add_code(conn, "Belonging", "#56B4E9")  # also at root
    cid_in = add_code(conn, "Existing", "#009E73", parent_id=fid)

    pre_source = _snapshot_scope(conn, None)
    pre_dest = _snapshot_scope(conn, fid)
    move_code_to_parent(conn, cid_a, fid)
    mgr.record_move_parent(
        cid_a,
        prev_parent_id=None,
        new_parent_id=fid,
        prev_source_ordering=pre_source,
        prev_dest_ordering=pre_dest,
    )

    assert mgr.undo(conn) is not None
    post_source = _snapshot_scope(conn, None)
    post_dest = _snapshot_scope(conn, fid)
    assert sorted(post_source) == sorted(pre_source)
    assert sorted(post_dest) == sorted(pre_dest)


def test_undo_indent_promote_to_folder_removes_folder_and_lifts_codes(conn):
    mgr = UndoManager()
    cid_a = add_code(conn, "Identity", "#D55E00")
    cid_b = add_code(conn, "Belonging", "#56B4E9")
    sort_a = conn.execute("SELECT sort_order FROM codebook_code WHERE id=?", (cid_a,)).fetchone()[0]
    sort_b = conn.execute("SELECT sort_order FROM codebook_code WHERE id=?", (cid_b,)).fetchone()[0]

    fid = add_folder(conn, "New folder")
    move_code_to_parent(conn, cid_a, fid)
    move_code_to_parent(conn, cid_b, fid)
    mgr.record_indent_promote_to_folder(
        folder_id=fid, code_ids=[cid_a, cid_b],
        prev_sort_orders=[sort_a, sort_b],
    )

    assert mgr.undo(conn) is not None
    folder_deleted = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id=?", (fid,)
    ).fetchone()[0]
    assert folder_deleted is not None
    for cid, prev_sort in [(cid_a, sort_a), (cid_b, sort_b)]:
        row = conn.execute(
            "SELECT parent_id, sort_order FROM codebook_code WHERE id=?", (cid,)
        ).fetchone()
        assert row["parent_id"] is None
        assert row["sort_order"] == prev_sort


def test_undo_delete_folder_cascade_relinks_children(conn):
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    affected_anns, affected_children = delete_code(conn, fid)
    mgr.record_delete_folder_cascade(
        folder_id=fid,
        child_ids=affected_children,
        annotation_ids=affected_anns,
    )

    assert mgr.undo(conn) is not None
    row = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id=?", (fid,)
    ).fetchone()
    assert row[0] is None
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id=?", (cid,)
    ).fetchone()[0]
    assert child_parent == fid
