"""Tests for folder CRUD and move ops on the codebook."""
import pytest

from ace.db.connection import create_project, open_project
from ace.models.codebook import (
    add_code,
    add_folder,
    convert_code_to_folder,
    delete_code,
    list_codes_with_tree,
    move_code_to_parent,
    restore_code,
)
from ace.models.annotation import add_annotation
from ace.models.assignment import add_assignment
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.models.codebook_invariants import InvariantError


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.ace"
    create_project(str(db), "Test")
    return open_project(str(db))


def test_add_folder_at_root(conn):
    fid = add_folder(conn, "Themes")
    row = conn.execute(
        "SELECT name, kind, colour, chord, parent_id "
        "FROM codebook_code WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["name"] == "Themes"
    assert row["kind"] == "folder"
    assert row["colour"] == ""
    assert row["chord"] is None
    assert row["parent_id"] is None


def test_move_code_to_folder(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00")
    move_code_to_parent(conn, cid, fid)
    parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert parent == fid


def test_move_code_to_root(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    move_code_to_parent(conn, cid, None)
    parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert parent is None


def test_move_code_under_code_rejected(conn):
    cid_a = add_code(conn, "A", "#D55E00")
    cid_b = add_code(conn, "B", "#56B4E9")
    with pytest.raises(InvariantError, match="parent must be a folder"):
        move_code_to_parent(conn, cid_b, cid_a)


def test_move_folder_under_folder(conn):
    fid_a = add_folder(conn, "Outer")
    fid_b = add_folder(conn, "Inner")
    move_code_to_parent(conn, fid_b, fid_a)
    parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (fid_b,)
    ).fetchone()[0]
    assert parent == fid_a


def test_move_folder_under_own_child_rejected(conn):
    outer = add_folder(conn, "Outer")
    inner = add_folder(conn, "Inner", parent_id=outer)
    with pytest.raises(InvariantError, match="own child"):
        move_code_to_parent(conn, outer, inner)


def test_convert_unannotated_code_to_folder(conn):
    cid = add_code(conn, "Theme", "#D55E00")
    result = convert_code_to_folder(conn, cid)

    row = conn.execute(
        "SELECT name, kind, colour, chord, parent_id FROM codebook_code WHERE id = ?",
        (cid,),
    ).fetchone()
    assert result["child_code_id"] is None
    assert result["annotation_ids"] == []
    assert row["name"] == "Theme"
    assert row["kind"] == "folder"
    assert row["colour"] == ""
    assert row["chord"] is None
    assert row["parent_id"] is None


def test_convert_annotated_code_to_folder_preserves_annotations(conn):
    cid = add_code(conn, "Theme", "#D55E00")
    sid = add_source(conn, "S001", "Important text.", "row")
    coder_id = list_coders(conn)[0]["id"]
    add_assignment(conn, sid, coder_id)
    ann_id = add_annotation(conn, sid, coder_id, cid, 0, 9, "Important")

    result = convert_code_to_folder(conn, cid)
    child_id = result["child_code_id"]

    parent = conn.execute(
        "SELECT name, kind, colour FROM codebook_code WHERE id = ?",
        (cid,),
    ).fetchone()
    child = conn.execute(
        "SELECT name, kind, colour, parent_id FROM codebook_code WHERE id = ?",
        (child_id,),
    ).fetchone()
    ann = conn.execute(
        "SELECT code_id FROM annotation WHERE id = ?",
        (ann_id,),
    ).fetchone()

    assert result["annotation_ids"] == [ann_id]
    assert parent["name"] == "Theme"
    assert parent["kind"] == "folder"
    assert parent["colour"] == ""
    assert child["name"] == "Theme"
    assert child["kind"] == "code"
    assert child["colour"] == "#D55E00"
    assert child["parent_id"] == cid
    assert ann["code_id"] == child_id


def test_list_codes_with_tree_returns_dfs_order(conn):
    fid = add_folder(conn, "Themes")
    add_code(conn, "Identity", "#D55E00", parent_id=fid)
    add_code(conn, "Belonging", "#56B4E9", parent_id=fid)
    add_code(conn, "Trust", "#0072B2")

    tree = list_codes_with_tree(conn)
    # Expect: [folder Themes, code Identity, code Belonging, code Trust]
    assert [r["kind"] for r in tree] == ["folder", "code", "code", "code"]
    assert [r["name"] for r in tree] == ["Themes", "Identity", "Belonging", "Trust"]
    # The folder row carries `child_ids` and `child_count`
    folder_row = tree[0]
    assert folder_row["child_count"] == 2


def test_list_codes_with_tree_returns_nested_folder_dfs_order(conn):
    outer = add_folder(conn, "Outer")
    inner = add_folder(conn, "Inner", parent_id=outer)
    leaf = add_code(conn, "Leaf", "#D55E00", parent_id=inner)
    root = add_code(conn, "Root", "#56B4E9")

    tree = list_codes_with_tree(conn)
    assert [r["name"] for r in tree] == ["Outer", "Inner", "Leaf", "Root"]
    assert [r["level"] for r in tree] == [1, 2, 3, 1]
    assert tree[0]["children"][0]["id"] == inner
    assert tree[0]["children"][0]["children"][0]["id"] == leaf
    assert tree[0]["root_nodes"][1]["id"] == root


def test_list_codes_with_tree_surfaces_orphan_codes(conn):
    """Codes whose parent_id refers to a soft-deleted folder show at root."""
    fid = add_folder(conn, "Themes")
    add_code(conn, "Identity", "#D55E00", parent_id=fid)
    # Soft-delete the folder directly (skip the cascade so child stays orphaned)
    conn.execute(
        "UPDATE codebook_code SET deleted_at = '2026-01-02' WHERE id = ?", (fid,)
    )
    conn.commit()
    tree = list_codes_with_tree(conn)
    # Folder is gone; Identity surfaces as a root code
    assert [r["kind"] for r in tree] == ["code"]
    assert tree[0]["name"] == "Identity"
    assert tree[0]["parent_id"] is None


def test_delete_folder_lifts_children_to_root(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    affected_annotations, affected_children = delete_code(conn, fid)
    assert affected_annotations == []
    assert affected_children == [cid]
    # Folder soft-deleted
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is not None
    # Child lifted to root
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert child_parent is None


def test_restore_folder_relinks_children(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    _, children_lifted = delete_code(conn, fid)
    restore_code(conn, fid, annotation_ids=[], children_lifted_ids=children_lifted)
    # Folder restored
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is None
    # Children re-linked
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert child_parent == fid
