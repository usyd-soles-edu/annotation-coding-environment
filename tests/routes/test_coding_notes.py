import json

import sqlite3

import pytest

from fastapi.testclient import TestClient

from ace.app import create_app

from ace.db.connection import create_project

from ace.models.codebook import add_code

from ace.models.project import list_coders

from ace.models.source import add_source

@pytest.fixture()
def client_with_sources(tmp_path):
    """Create a project with 3 sources, 2 codes, and a coder."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    # create_project auto-creates a "default" coder
    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    # Add sources
    add_source(conn, "S001", "First document content for coding.", "row")
    add_source(conn, "S002", "Second document with different text.", "row")
    add_source(conn, "S003", "Third document for testing purposes.", "row")

    # Add codes
    add_code(conn, "Theme A", "#BF6030")
    add_code(conn, "Theme B", "#30A64E")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        yield client, coder_id


@pytest.fixture()
def client_with_sources_no_codes(tmp_path):
    """Create a project with sources and a coder, but no codes."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    add_source(conn, "S001", "First document content for coding.", "row")
    add_source(conn, "S002", "Second document with different text.", "row")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        yield client


@pytest.fixture()
def client_with_codes(tmp_path):
    """Like client_with_sources but also returns code IDs and db_path."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    add_source(conn, "S001", "First document content for coding.", "row")
    add_source(conn, "S002", "Second document with different text.", "row")

    code_a = add_code(conn, "Theme A", "#BF6030")
    code_b = add_code(conn, "Theme B", "#30A64E")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        # Visit the coding page once to auto-create assignments
        client.get("/code")
        yield client, coder_id, code_a, code_b, str(db_path)


def _count_active_annotations(client, db_path: str, source_index: int) -> int:
    """Count non-deleted annotations on the source at source_index."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute(
            "SELECT id FROM source ORDER BY sort_order LIMIT 1 OFFSET ?",
            (source_index,),
        ).fetchone()
        assert source_row is not None, f"no source at index {source_index}"
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM annotation "
            "WHERE source_id = ? AND deleted_at IS NULL",
            (source_row["id"],),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def _active_annotation_ranges(db_path: str, source_index: int) -> list[tuple[int, int]]:
    """Return [(start_offset, end_offset), ...] for active annotations, ordered by start."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute(
            "SELECT id FROM source ORDER BY sort_order LIMIT 1 OFFSET ?",
            (source_index,),
        ).fetchone()
        rows = conn.execute(
            "SELECT start_offset, end_offset FROM annotation "
            "WHERE source_id = ? AND deleted_at IS NULL "
            "ORDER BY start_offset",
            (source_row["id"],),
        ).fetchall()
        return [(r["start_offset"], r["end_offset"]) for r in rows]
    finally:
        conn.close()


def _latest_id_by_name(db_path: str, name: str, kind: str) -> str:
    """Return the id of the most-recently-created row matching name+kind."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id FROM codebook_code "
        "WHERE name = ? AND kind = ? AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 1",
        (name, kind),
    ).fetchone()
    conn.close()
    assert row is not None, f"no {kind} named {name!r} found in {db_path}"
    return row["id"]


def _extract_folder_id(_html: str, name: str, db_path: str) -> str:
    """Resolve a folder's id via the database (HTML markup is Task 6)."""
    return _latest_id_by_name(db_path, name, "folder")


def _create_folder(client, name: str, db_path: str) -> str:
    """POST /api/codes/folder and return the new folder id."""
    r = client.post(
        "/api/codes/folder",
        data={"name": name, "current_index": 0},
    )
    assert r.status_code == 200, r.text
    return _latest_id_by_name(db_path, name, "folder")


def _add_test_code(
    client, name: str, db_path: str, parent_id: str | None = None,
) -> str:
    """POST /api/codes and return the new code id."""
    data = {"name": name, "current_index": 0}
    if parent_id is not None:
        data["parent_id"] = parent_id
    r = client.post("/api/codes", data=data)
    assert r.status_code == 200, r.text
    return _latest_id_by_name(db_path, name, "code")


def _sort_orders_at_root(db_path: str) -> dict[str, int]:
    """Return {code_id: sort_order} for every active code at root scope."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL AND parent_id IS NULL AND kind = 'code'"
    ).fetchall()
    conn.close()
    return {r["id"]: r["sort_order"] for r in rows}


def _sort_orders_in_folder(db_path: str, folder_id: str) -> dict[str, int]:
    """Return {code_id: sort_order} for every active code parented to folder."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL AND parent_id = ? AND kind = 'code'",
        (folder_id,),
    ).fetchall()
    conn.close()
    return {r["id"]: r["sort_order"] for r in rows}


def _code_colours(db_path: str, code_ids: list[str]) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(code_ids))
    rows = conn.execute(
        f"SELECT id, colour FROM codebook_code WHERE id IN ({placeholders})",
        code_ids,
    ).fetchall()
    conn.close()
    return {r["id"]: r["colour"] for r in rows}


@pytest.fixture()
def client_with_two_sentences(tmp_path):
    """Project with a single source containing two adjacent sentences + 1 code.

    The source text splits into exactly two sentences so the merge branch
    (apply same code to an adjacent sentence) is reachable.
    """
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    add_source(conn, "S001", "First sentence here. Second sentence now.", "row")
    code_a = add_code(conn, "Theme A", "#BF6030")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")
        yield client, coder_id, code_a, str(db_path)


def test_coding_page_renders(client_with_sources):
    """GET /code renders the coding page with swap zones."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "coding-workspace" in resp.text
    assert "code-sidebar" in resp.text
    assert "text-panel" in resp.text
    assert "ace-legend" in resp.text
    # Source notes UI (Task R1 — drawer pattern)
    assert 'id="note-pill"' in resp.text
    assert 'id="note-drawer"' in resp.text
    assert 'id="note-textarea"' in resp.text
    assert 'role="complementary"' in resp.text


def test_undo_cross_source_falls_back_when_source_unassigned(client_with_codes):
    """Undo where the action's source has been removed from the assignment list
    stays on the current source and notes 'no longer assigned' in the status."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply on source 0 (records add against source 0's id)
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })

    # Programmatically delete source 0's assignment row to simulate the source
    # being removed from the coder's assignment list after the action was recorded.
    # (Sources are 1-indexed by sort_order; the first source is the one with the
    # smallest sort_order.)
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM assignment WHERE source_id = ("
        "SELECT id FROM source ORDER BY sort_order LIMIT 1"
        ")"
    )
    conn.commit()
    conn.close()

    # Undo. Only one assignment remains (S002 at index 0); the action's source
    # (S001) is no longer in the list, so the route should fall back to the
    # current source and append "(source no longer assigned)" to the status.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "no longer assigned" in resp.text
    # No navigate trigger, since the source's index can't be located.
    assert "ace-navigate" not in resp.headers.get("HX-Trigger", "")


def test_coding_context_includes_note_state(client_with_codes):
    """_coding_context exposes note text, has_note flag, and notes presence set."""
    import sqlite3
    from ace.models.assignment import get_assignments_for_coder
    from ace.models.source_note import upsert_note
    from ace.routes.pages import _coding_context

    client, coder_id, code_a, code_b, db_path = client_with_codes

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        assignments = get_assignments_for_coder(conn, coder_id)
        s1 = assignments[0]["source_id"]
        s2 = assignments[1]["source_id"]

        # No notes initially
        ctx0 = _coding_context(conn, coder_id, 0)
        assert ctx0["current_note_text"] == ""
        assert ctx0["has_note"] is False
        assert ctx0["source_ids_with_notes"] == set()

        # Add a note on source 1, view source 1
        upsert_note(conn, s1, coder_id, "Hello note")
        ctx1 = _coding_context(conn, coder_id, 0)
        assert ctx1["current_note_text"] == "Hello note"
        assert ctx1["has_note"] is True
        assert ctx1["source_ids_with_notes"] == {s1}

        # View source 2 — different has_note state, same presence set
        ctx2 = _coding_context(conn, coder_id, 1)
        assert ctx2["current_note_text"] == ""
        assert ctx2["has_note"] is False
        assert ctx2["source_ids_with_notes"] == {s1}

        # Add a second note
        upsert_note(conn, s2, coder_id, "Another")
        ctx3 = _coding_context(conn, coder_id, 1)
        assert ctx3["has_note"] is True
        assert ctx3["source_ids_with_notes"] == {s1, s2}
    finally:
        conn.close()


def test_coding_context_emits_sources_json(client_with_codes):
    """sources_json is a flat per-source array suitable for client rendering."""
    import sqlite3
    from ace.routes.pages import _coding_context

    client, coder_id, code_a, _, db_path = client_with_codes
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ctx = _coding_context(conn, coder_id, 0)
    finally:
        conn.close()

    assert "sources_json" in ctx
    data = ctx["sources_json"]
    assert isinstance(data, list)
    assert len(data) == ctx["total_sources"]

    first = data[0]
    for key in ("index", "source_id", "display_id", "count", "flagged", "note"):
        assert key in first, f"sources_json[0] missing key {key!r}"
    assert first["index"] == 0
    assert isinstance(first["count"], int)
    assert isinstance(first["flagged"], bool)
    assert isinstance(first["note"], bool)
    # No annotations yet → count is 0, flags all false
    assert first["count"] == 0
    assert first["flagged"] is False
    assert first["note"] is False
