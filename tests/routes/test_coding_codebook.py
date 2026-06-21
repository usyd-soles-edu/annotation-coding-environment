import json
import re

import sqlite3
from pathlib import Path

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


def assert_audit_codebook_response(resp):
    assert resp.status_code == 200
    assert resp.headers.get("HX-Reswap") == "none"
    assert re.search(
        r'<[^>]+id="code-sidebar"[^>]+hx-swap-oob="outerHTML"[^>]*>',
        resp.text,
    )
    assert 'data-codebook-mode="audit"' in resp.text
    assert 'id="text-panel"' not in resp.text
    assert 'id="ace-ann-data"' not in resp.text
    assert 'id="ace-sources-data"' not in resp.text


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


def test_coding_page_empty_codebook_shows_first_actions(client_with_sources_no_codes):
    """A project with sources but no codes exposes first-action buttons."""
    resp = client_with_sources_no_codes.get("/code")
    assert resp.status_code == 200
    assert "ace-headless-tree-preview--empty" in resp.text
    assert 'id="create-first-code-btn"' in resp.text
    assert 'id="empty-import-codebook-btn"' in resp.text
    assert "Create first code" in resp.text
    assert "Import codebook CSV" in resp.text
    assert "<kbd>/code</kbd>" in resp.text


def test_coding_sidebar_declares_coding_mode(client_with_codes):
    """Code sidebar renders with explicit coding mode in the coding route."""
    client, *_ = client_with_codes
    resp = client.get("/code")
    assert resp.status_code == 200
    assert 'data-codebook-mode="coding"' in resp.text
    assert "Press Enter to apply" in resp.text


def test_codebook_import_preview_uses_compact_mapping_dialog(
    client_with_sources_no_codes, tmp_path
):
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text(
        "Code Label,Theme,Dictionary Definition\n"
        "Access,Equity,Barriers to using a service\n"
    )

    resp = client_with_sources_no_codes.post(
        "/api/codes/import/preview-path",
        data={"path": str(csv_path), "current_index": 0},
    )

    assert resp.status_code == 200
    assert "ace-codebook-import-dialog" in resp.text
    assert 'id="codebook-map-name"' in resp.text
    assert 'value="Code Label" selected' in resp.text
    assert 'id="codebook-map-group"' in resp.text
    assert 'value="Theme" selected' in resp.text
    assert 'id="codebook-map-definition"' in resp.text
    assert 'value="Dictionary Definition" selected' in resp.text
    assert "Sidebar preview" in resp.text
    assert "Barriers to using a service" in resp.text


def test_codebook_export_removes_temp_file(client_with_sources, tmp_path, monkeypatch):
    """The codebook export route removes its temporary CSV after serving it."""
    import tempfile

    import ace.routes.api_codebook as api_codebook

    client, _coder_id = client_with_sources
    temp_paths = []
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def _named_temp_in_tmp_path(*args, **kwargs):
        kwargs["dir"] = tmp_path
        tmp = original_named_temporary_file(*args, **kwargs)
        temp_paths.append(tmp.name)
        return tmp

    monkeypatch.setattr(
        api_codebook.tempfile,
        "NamedTemporaryFile",
        _named_temp_in_tmp_path,
    )

    resp = client.get("/api/codes/export")

    assert resp.status_code == 200
    assert temp_paths
    assert not any(Path(path).exists() for path in temp_paths)


def test_codebook_import_preview_map_returns_definition_payload(
    client_with_sources_no_codes, tmp_path
):
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text(
        "Code Label,Theme,Dictionary Definition\n"
        "Access,Equity,Barriers to using a service\n"
    )

    resp = client_with_sources_no_codes.post(
        "/api/codes/import/preview-map",
        data={
            "path": str(csv_path),
            "name_column": "Code Label",
            "group_column": "Theme",
            "definition_column": "Dictionary Definition",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["new_count"] == 1
    assert "Barriers to using a service" in payload["preview_html"]
    codes = json.loads(payload["codes_json"])
    assert codes[0]["definition"] == "Barriers to using a service"
    assert codes[0]["group_name"] == "Equity"


def test_codebook_import_preview_map_respects_no_definition_selection(
    client_with_sources_no_codes, tmp_path
):
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text(
        "Code Label,Theme,Dictionary Definition\n"
        "Access,Equity,Barriers to using a service\n"
    )

    resp = client_with_sources_no_codes.post(
        "/api/codes/import/preview-map",
        data={
            "path": str(csv_path),
            "name_column": "Code Label",
            "group_column": "Theme",
            "definition_column": "",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "Barriers to using a service" not in payload["preview_html"]
    codes = json.loads(payload["codes_json"])
    assert codes[0]["definition"] is None


def test_codebook_import_route_stores_definition(client_with_sources_no_codes):
    from ace.db.connection import open_project

    codes_json = json.dumps([
        {
            "name": "Access",
            "colour": "#123456",
            "group_name": "Equity",
            "definition": "Barriers to using a service",
        }
    ])

    resp = client_with_sources_no_codes.post(
        "/api/codes/import",
        data={"codes_json": codes_json, "current_index": 0},
    )

    assert resp.status_code == 200
    conn = open_project(client_with_sources_no_codes.app.state.project_path)
    try:
        row = conn.execute(
            "SELECT definition FROM codebook_code WHERE name = 'Access'"
        ).fetchone()
    finally:
        conn.close()
    assert row["definition"] == "Barriers to using a service"


def test_codebook_tree_route_returns_headless_tree_item_map(client_with_codes):
    """GET /api/codes/tree exposes ACE rows in a Headless Tree-friendly shape."""
    from ace.db.connection import open_project
    from ace.models.annotation import add_annotation
    from ace.models.codebook import add_code, add_folder

    client, coder_id, _code_a, _code_b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        source_id = conn.execute(
            "SELECT id FROM source ORDER BY sort_order LIMIT 1"
        ).fetchone()["id"]
        parent = add_folder(conn, "Parent folder")
        child = add_code(
            conn,
            "Nested code",
            "#123456",
            parent_id=parent,
            definition="Definition imported from a dictionary column",
        )
        add_annotation(conn, source_id, coder_id, child, 0, 5, "First")
    finally:
        conn.close()

    resp = client.get("/api/codes/tree")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["root_id"] == "root"
    assert parent in payload["items"]["root"]["children"]
    assert payload["items"][parent] == {
        "id": parent,
        "name": "Parent folder",
        "kind": "folder",
        "parent_id": None,
        "level": 1,
        "sort_order": payload["items"][parent]["sort_order"],
        "children": [child],
        "child_count": 1,
        "count": 0,
    }
    assert payload["items"][child] == {
        "id": child,
        "name": "Nested code",
        "kind": "code",
        "parent_id": parent,
        "level": 2,
        "sort_order": payload["items"][child]["sort_order"],
        "children": [],
        "child_count": 0,
        "count": 1,
        "colour": "#123456",
        "chord": None,
        "definition": "Definition imported from a dictionary column",
    }


def test_codebook_tree_route_handles_empty_codebook(client_with_sources_no_codes):
    """The JSON tree route gives the future island a stable empty state."""
    resp = client_with_sources_no_codes.get("/api/codes/tree")

    assert resp.status_code == 200
    assert resp.json() == {
        "root_id": "root",
        "items": {
            "root": {
                "id": "root",
                "name": "Root",
                "kind": "folder",
                "parent_id": None,
                "level": 0,
                "children": [],
                "child_count": 0,
                "count": 0,
            }
        },
    }


def test_sidebar_dropdown_carries_keyboard_shortcuts(client_with_sources):
    """The gear dropdown absorbs the old `?` button as its first item."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="codebook-menu-shortcuts-btn"' in body
    assert ">Keyboard shortcuts<" in body
    # Sits at the top of the dropdown — before the import/export group.
    shortcuts_pos = body.index("codebook-menu-shortcuts-btn")
    import_pos = body.index("codebook-menu-import-btn")
    assert shortcuts_pos < import_pos


def test_code_rename_records_undo_entry(client_with_codes):
    """PUT /api/codes/{code_id} with new name records code_rename."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes
    resp = client.put(f"/api/codes/{code_id}", data={
        "name": "RenamedCode", "current_index": 0,
    })
    assert resp.status_code == 200

    # Sanity: rename did happen
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    conn.close()
    assert row["name"] == "RenamedCode"

    # Undo
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Undone:" in resp.text

    # Verify the rename was undone in the DB (status bar text mentions the
    # new name in the "back to" description, so an HTML-text assertion is
    # ambiguous — go to the source of truth).
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    conn.close()
    assert row["name"] == "Theme A"


def test_audit_mode_create_code_returns_audit_sidebar_only(client_with_codes):
    client, _coder_id, code_id, _other_code_id, _db_path = client_with_codes
    resp = client.post(
        "/api/codes",
        data={
            "name": "Audit code",
            "current_index": 0,
            "codebook_mode": "audit",
            "current_code_id": code_id,
        },
    )
    assert_audit_codebook_response(resp)


def test_audit_mode_create_folder_returns_audit_sidebar_only(client_with_codes):
    client, _coder_id, code_id, _other_code_id, _db_path = client_with_codes
    resp = client.post(
        "/api/codes/folder",
        data={
            "name": "Audit folder",
            "current_index": 0,
            "codebook_mode": "audit",
            "current_code_id": code_id,
        },
    )
    assert_audit_codebook_response(resp)


def test_audit_mode_rename_returns_audit_sidebar_only(client_with_codes):
    client, _coder_id, code_id, _other_code_id, _db_path = client_with_codes
    resp = client.put(
        f"/api/codes/{code_id}",
        data={
            "name": "Renamed in audit",
            "current_index": 0,
            "codebook_mode": "audit",
            "current_code_id": code_id,
        },
    )
    assert_audit_codebook_response(resp)


def test_audit_rename_response_marks_current_code_reload(client_with_codes):
    client, _coder_id, code_id, _other_code_id, _db_path = client_with_codes
    resp = client.put(
        f"/api/codes/{code_id}",
        data={
            "name": "Audit renamed",
            "codebook_mode": "audit",
            "current_code_id": code_id,
        },
    )
    assert_audit_codebook_response(resp)
    trigger = resp.headers.get("HX-Trigger", "")
    assert '"ace:codebook-mutated"' in trigger
    assert '"mode": "audit"' in trigger
    assert '"operation": "update"' in trigger
    assert f'"affectedCodeIds": ["{code_id}"]' in trigger
    assert f'"currentCodeId": "{code_id}"' in trigger
    assert '"auditReload": true' in trigger


def test_undo_code_rename_no_navigate_trigger(client_with_codes):
    """Undoing a codebook-only op (rename) must not emit ace-navigate."""
    client, _coder_id, code_id, _, _db_path = client_with_codes

    resp = client.put(f"/api/codes/{code_id}", data={
        "name": "RenamedCode", "current_index": 0,
    })
    assert resp.status_code == 200

    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "ace-navigate" not in resp.headers.get("HX-Trigger", "")


def test_undo_code_delete_restores_across_sources(client_with_codes):
    """Deleting a code with annotations on multiple sources soft-deletes them
    all; undo restores every annotation to active state."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply the code on source 0 and source 1 (fixture has 2 sources).
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    client.post("/api/code/apply", data={
        "current_index": 1, "code_id": code_id,
        "start_offset": 0, "end_offset": 6, "selected_text": "Second",
    })

    # Sanity: 2 active annotations before delete.
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert active == 2

    # Delete the code — should cascade soft-delete both annotations.
    resp = client.delete(
        f"/api/codes/{code_id}", params={"current_index": 0}
    )
    assert resp.status_code == 200

    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert active == 0

    # Undo — both annotations restored to active state.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200

    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 2


def test_audit_mode_delete_returns_audit_sidebar_only(client_with_codes):
    client, _coder_id, code_id, _other_code_id, _db_path = client_with_codes
    resp = client.delete(
        f"/api/codes/{code_id}",
        params={
            "current_index": 0,
            "codebook_mode": "audit",
            "current_code_id": code_id,
        },
    )
    assert_audit_codebook_response(resp)


def test_reorder_codes_noop_does_not_record_undo_entry(client_with_codes):
    """A POST /api/codes/reorder that doesn't change ordering must NOT
    record an undo entry. The client uses this endpoint to re-render the
    sidebar after side-channel mutations; without this guard, one user
    drag takes two undo presses to reverse.
    """
    client, coder_id, code_a, code_b, db_path = client_with_codes

    # First, do a real reorder (swap the two codes) — should record one entry.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": json.dumps([code_b, code_a]), "current_index": 0},
    )
    assert resp.status_code == 200

    # Now a no-op reorder (same order) — should NOT record another entry.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": json.dumps([code_b, code_a]), "current_index": 0},
    )
    assert resp.status_code == 200

    # And the empty-list "refresh" pattern from _refreshSidebar — also no-op.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": "[]", "current_index": 0},
    )
    assert resp.status_code == 200

    # One undo should fully reverse the swap. After it, second undo says nothing.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Undone:" in resp.text

    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to undo" in resp.text


def test_invalid_code_name_returns_status_oob_swap(client_with_codes):
    """Code validation error returns an OOB swap into the status bar, not #toast."""
    client, _coder, _a, _b, _path = client_with_codes
    # Whitespace-only name passes Form(...) presence check but fails .strip() guard
    resp = client.post("/api/codes", data={"name": "   "})
    assert resp.status_code == 200
    assert "ace-statusbar-event" in resp.text
    # Errors must also reach screen readers via the assertive live region.
    assert "ace-live-region-assertive" in resp.text
    assert 'id="toast"' not in resp.text


def test_annotate_rejects_folder_id(client_with_codes):
    client, coder_id, _code_a, _code_b, db_path = client_with_codes
    client.cookies.set("coder_id", coder_id)
    folder_id = _create_folder(client, "Themes", db_path)

    resp = client.post(
        "/api/code/apply",
        data={
            "code_id": folder_id,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert resp.status_code == 400


def test_create_folder_route(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    r = client.post(
        "/api/codes/folder",
        data={"name": "Themes", "current_index": 0},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    # Folder row exists in the DB with kind='folder'
    fid = _latest_id_by_name(db_path, "Themes", "folder")
    assert fid


def test_set_parent_to_folder(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path)
    before_colours = _code_colours(db_path, [code_id])

    r = client.put(
        f"/api/codes/{code_id}/parent",
        data={"parent_id": folder_id, "current_index": 0},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] == folder_id
    assert _code_colours(db_path, [code_id]) == before_colours


def test_set_folder_parent_to_folder(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    outer_id = _create_folder(client, "Outer", db_path)
    inner_id = _create_folder(client, "Inner", db_path)

    r = client.put(
        f"/api/codes/{inner_id}/parent",
        data={"parent_id": outer_id, "current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (inner_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] == outer_id


def test_set_folder_parent_to_descendant_rejected(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    outer_id = _create_folder(client, "Outer", db_path)
    inner_id = _create_folder(client, "Inner", db_path)
    client.put(
        f"/api/codes/{inner_id}/parent",
        data={"parent_id": outer_id, "current_index": 0},
    )

    r = client.put(
        f"/api/codes/{outer_id}/parent",
        data={"parent_id": inner_id, "current_index": 0},
    )
    assert r.status_code == 400


def test_set_parent_to_root(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path, parent_id=folder_id)
    before_colours = _code_colours(db_path, [code_id])

    r = client.put(
        f"/api/codes/{code_id}/parent",
        data={"parent_id": "", "current_index": 0},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] is None
    assert _code_colours(db_path, [code_id]) == before_colours


def test_set_parent_to_code_rejected(client_with_codes):
    client, _coder_id, code_a, code_b, _db_path = client_with_codes
    # Both code_a and code_b are kind='code'. Moving b under a must fail.
    r = client.put(
        f"/api/codes/{code_b}/parent",
        data={"parent_id": code_a, "current_index": 0},
    )
    assert r.status_code == 400


def test_cut_paste_moves_code(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path)

    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_id, "target_id": folder_id, "current_index": 0},
    )
    assert r.status_code == 200

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] == folder_id


def test_rename_group_route_removed(client_with_codes):
    client, *_ = client_with_codes
    r = client.put(
        "/api/codes/rename-group",
        data={"old_name": "x", "new_name": "y"},
    )
    assert r.status_code == 404


def test_indent_promote_creates_folder_and_moves_both_codes(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    a = _add_test_code(client, "Alpha", db_path)
    b = _add_test_code(client, "Beta", db_path)
    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": a,
            "folder_name": "Wrapped",
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    # Folder exists; both codes parented to it.
    fid = _latest_id_by_name(db_path, "Wrapped", "folder")
    assert fid
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, parent_id FROM codebook_code WHERE id IN (?, ?)",
        (a, b),
    ).fetchall()
    conn.close()
    parents = {r["id"]: r["parent_id"] for r in rows}
    assert parents[a] == fid
    assert parents[b] == fid


def test_indent_promote_rolls_back_on_name_collision(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    # Pre-create the folder name we'll collide with.
    existing = _create_folder(client, "Taken", db_path)
    a = _add_test_code(client, "Alpha", db_path)
    b = _add_test_code(client, "Beta", db_path)

    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": a,
            "folder_name": "Taken",
            "current_index": 0,
        },
    )
    # Returns OOB status fragment (200) carrying the error message; transaction rolled back.
    assert r.status_code == 200
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, parent_id FROM codebook_code WHERE id IN (?, ?)",
        (a, b),
    ).fetchall()
    # Confirm only one folder named 'Taken' (the pre-existing one).
    folder_count = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Taken' AND kind = 'folder' AND deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert folder_count == 1
    parents = {r["id"]: r["parent_id"] for r in rows}
    # Both codes still at root — no half-built folder, no orphan move.
    assert parents[a] is None
    assert parents[b] is None
    assert existing  # silence unused-var lint


def test_indent_promote_invalid_above_code_id_returns_400(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    b = _add_test_code(client, "Beta", db_path)
    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": "does-not-exist",
            "folder_name": "Wrapped",
            "current_index": 0,
        },
    )
    assert r.status_code == 400


def test_reorder_in_scope_updates_sort_order_within_root(client_with_codes):
    """POST /api/codes/reorder-in-scope rewrites sort_order for the listed
    ids in the order they're passed (root scope = empty parent_id)."""
    client, _coder_id, a, b, db_path = client_with_codes
    cc = _add_test_code(client, "Charlie", db_path)

    # Reorder root: Charlie, Alpha (a), Bravo (b)
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([cc, a, b]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    orders = _sort_orders_at_root(db_path)
    assert orders[cc] == 0
    assert orders[a] == 1
    assert orders[b] == 2


def test_reorder_in_scope_preserves_code_colours(client_with_codes):
    client, _coder_id, a, b, db_path = client_with_codes
    cc = _add_test_code(client, "Charlie", db_path)
    before = _code_colours(db_path, [a, b, cc])

    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([cc, b, a]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    assert _code_colours(db_path, [a, b, cc]) == before


def test_reorder_in_scope_returns_text_panel_and_sidebar(client_with_codes):
    """The route returns the unified `_render_full_coding_oob` shape so the
    count chips on the text panel + sidebar stay in sync."""
    client, _coder_id, a, b, _db_path = client_with_codes
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([b, a]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200
    # text-panel primary swap + sidebar OOB
    assert 'id="text-panel"' in r.text
    assert 'id="code-sidebar"' in r.text
    assert 'hx-swap-oob' in r.text


def test_audit_mode_reorder_in_scope_returns_audit_sidebar_only(client_with_codes):
    client, _coder_id, a, b, _db_path = client_with_codes
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([b, a]),
            "parent_id": "",
            "current_index": 0,
            "codebook_mode": "audit",
            "current_code_id": a,
        },
    )
    assert_audit_codebook_response(r)


def test_reorder_in_scope_within_folder(client_with_codes):
    """Reorder works within a folder scope — only rows under that parent
    get their sort_order updated."""
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    x = _add_test_code(client, "FX", db_path, parent_id=folder_id)
    y = _add_test_code(client, "FY", db_path, parent_id=folder_id)
    z = _add_test_code(client, "FZ", db_path, parent_id=folder_id)

    # Reorder folder: FZ, FX, FY
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([z, x, y]),
            "parent_id": folder_id,
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    orders = _sort_orders_in_folder(db_path, folder_id)
    assert orders[z] == 0
    assert orders[x] == 1
    assert orders[y] == 2


def test_reorder_in_scope_ignores_codes_outside_scope(client_with_codes):
    """If the client sends ids that live in a different scope, the UPDATE
    is filtered to the requested parent — out-of-scope rows are untouched.

    This is defensive: a stale client (e.g. mid-drag DOM) can't accidentally
    move a code from one folder into another via the reorder endpoint.
    """
    client, _coder_id, root_a, root_b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    inside = _add_test_code(client, "Inside", db_path, parent_id=folder_id)

    before_root = _sort_orders_at_root(db_path)
    before_folder = _sort_orders_in_folder(db_path, folder_id)

    # Pretend client (incorrectly) lists a root code in the folder scope.
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([inside, root_a]),
            "parent_id": folder_id,
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    after_root = _sort_orders_at_root(db_path)
    after_folder = _sort_orders_in_folder(db_path, folder_id)

    # root_a's sort_order must NOT have changed (it's still in root scope).
    assert after_root[root_a] == before_root[root_a]
    assert after_root[root_b] == before_root[root_b]
    # The in-scope row was renumbered to position 0.
    assert after_folder[inside] == 0
    # No spurious row got reparented.
    assert set(after_folder.keys()) == set(before_folder.keys())


def test_reorder_in_scope_records_undo(client_with_codes):
    """Drag-reorder must be undoable — a Z press right after a swap puts
    the codes back in their previous order. Regression guard: the route
    used to silently skip undo, so Z would either pop an unrelated entry
    or report "Nothing to undo"."""
    client, _coder_id, a, b, db_path = client_with_codes

    before = _sort_orders_at_root(db_path)

    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([b, a]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200
    after_swap = _sort_orders_at_root(db_path)
    assert after_swap[b] < after_swap[a], "swap should put b before a"

    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert "Undone:" in r.text

    after_undo = _sort_orders_at_root(db_path)
    assert after_undo == before, "undo must restore prior sort_order"


def test_reorder_in_scope_noop_does_not_record(client_with_codes):
    """Re-saving the current order is a no-op — the undo stack stays clean
    so one user drag is one Z press, not two. Mirrors the legacy
    /codes/reorder no-op behaviour."""
    client, _coder_id, a, b, _db_path = client_with_codes

    # Real swap first to land sort_order at 0,1 (the route always renumbers
    # from 0, so the fixture's 1,2 needs to be normalised before identity
    # comparisons make sense).
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={"code_ids": json.dumps([b, a]), "parent_id": "", "current_index": 0},
    )
    assert r.status_code == 200

    # Identity reorder of the new state — should NOT record an entry.
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={"code_ids": json.dumps([b, a]), "parent_id": "", "current_index": 0},
    )
    assert r.status_code == 200

    # First undo reverses the swap; second says nothing — confirms the
    # identity call did not push.
    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert "Undone:" in r.text
    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert "Nothing to undo" in r.text


def test_reorder_in_scope_invalid_json_returns_oob_status(client_with_codes):
    """Malformed code_ids must not 500 — return an OOB status fragment."""
    client, *_ = client_with_codes
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": "not-json",
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200
    assert "Invalid code_ids format" in r.text


def test_create_code_palette_unaffected_by_folder_count(client_with_codes):
    """F2 — `create_code` palette index counts only code rows, not folders.

    Two scenarios with the same code-count must yield the same colour even
    when the second one has extra folders sitting between them.
    """
    from ace.db.connection import open_project
    from ace.models.codebook import COLOUR_PALETTE

    client, _coder, _a, _b, db_path = client_with_codes

    # Baseline: two codes already exist (Theme A, Theme B). Next palette
    # slot for a freshly-created code should be index 2.
    expected_colour = COLOUR_PALETTE[2][0]

    r = client.post("/api/codes", data={"name": "Charlie", "current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT colour FROM codebook_code WHERE name = ?", ("Charlie",)
        ).fetchone()
    finally:
        conn.close()
    assert row["colour"].upper() == expected_colour.upper()

    # Create a folder, then a fourth code. With folders included in the
    # palette index (the bug), the colour would shift by one. The fix
    # filters `kind = 'code'`, so the next colour stays at palette[3].
    r = client.post("/api/codes/folder", data={"name": "Themes", "current_index": 0})
    assert r.status_code == 200

    expected_after_folder = COLOUR_PALETTE[3][0]
    r = client.post("/api/codes", data={"name": "Delta", "current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT colour FROM codebook_code WHERE name = ?", ("Delta",)
        ).fetchone()
    finally:
        conn.close()
    assert row["colour"].upper() == expected_after_folder.upper()


def test_delete_code_404_on_unknown_id(client_with_codes):
    """F4 — DELETE /api/codes/{id} returns 404 for a missing id, no undo entry."""
    client, *_ = client_with_codes
    r = client.delete("/api/codes/this-id-does-not-exist", params={"current_index": 0})
    assert r.status_code == 404

    # The 404 should NOT have pushed an undo entry.
    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert "Nothing to undo" in r.text


def test_cut_paste_to_root_with_empty_target(client_with_codes):
    """F5 — POST /api/codes/cut-paste accepts target_id="" as 'paste to root'."""
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder, move_code_to_parent

    client, _coder, code_a, _b, db_path = client_with_codes

    # Move Theme A into a folder so we have something to "cut back to root".
    conn = open_project(db_path)
    try:
        fid = add_folder(conn, "Themes")
        move_code_to_parent(conn, code_a, fid)
    finally:
        conn.close()

    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_a, "target_id": "", "current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = open_project(db_path)
    try:
        parent = conn.execute(
            "SELECT parent_id FROM codebook_code WHERE id = ?", (code_a,)
        ).fetchone()["parent_id"]
    finally:
        conn.close()
    assert parent is None, "code should be back at root scope"


def test_cut_paste_404_on_unknown_target(client_with_codes):
    """F5 sibling — non-empty target_id that doesn't exist still 404s."""
    client, _coder, code_a, _b, _db = client_with_codes
    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_a, "target_id": "no-such-id", "current_index": 0},
    )
    assert r.status_code == 404


def test_convert_unannotated_code_to_folder_route_records_undo(client_with_codes):
    from ace.db.connection import open_project

    client, _coder, code_a, _b, db_path = client_with_codes

    r = client.post(
        f"/api/codes/{code_a}/convert-to-folder",
        data={"current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT kind, colour FROM codebook_code WHERE id = ?",
            (code_a,),
        ).fetchone()
    finally:
        conn.close()
    assert row["kind"] == "folder"
    assert row["colour"] == ""

    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT kind, colour FROM codebook_code WHERE id = ?",
            (code_a,),
        ).fetchone()
    finally:
        conn.close()
    assert row["kind"] == "code"
    assert row["colour"] == "#BF6030"


def test_convert_annotated_code_to_folder_route_preserves_annotations(client_with_codes):
    from ace.db.connection import open_project
    from ace.models.annotation import add_annotation

    client, coder_id, code_a, _b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        source_id = conn.execute("SELECT id FROM source ORDER BY display_id LIMIT 1").fetchone()["id"]
        ann_id = add_annotation(conn, source_id, coder_id, code_a, 0, 5, "First")
    finally:
        conn.close()

    r = client.post(
        f"/api/codes/{code_a}/convert-to-folder",
        data={"current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = open_project(db_path)
    try:
        parent = conn.execute(
            "SELECT kind, colour FROM codebook_code WHERE id = ?",
            (code_a,),
        ).fetchone()
        child = conn.execute(
            "SELECT id, kind, name, colour, parent_id, deleted_at "
            "FROM codebook_code WHERE parent_id = ? AND kind = 'code'",
            (code_a,),
        ).fetchone()
        ann = conn.execute(
            "SELECT code_id FROM annotation WHERE id = ?",
            (ann_id,),
        ).fetchone()
    finally:
        conn.close()

    assert parent["kind"] == "folder"
    assert parent["colour"] == ""
    assert child["name"] == "Theme A"
    assert child["colour"] == "#BF6030"
    assert child["deleted_at"] is None
    assert ann["code_id"] == child["id"]

    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        parent = conn.execute(
            "SELECT kind, colour FROM codebook_code WHERE id = ?",
            (code_a,),
        ).fetchone()
        child_after_undo = conn.execute(
            "SELECT deleted_at FROM codebook_code WHERE id = ?",
            (child["id"],),
        ).fetchone()
        ann_after_undo = conn.execute(
            "SELECT code_id FROM annotation WHERE id = ?",
            (ann_id,),
        ).fetchone()
    finally:
        conn.close()
    assert parent["kind"] == "code"
    assert parent["colour"] == "#BF6030"
    assert child_after_undo["deleted_at"] is not None
    assert ann_after_undo["code_id"] == code_a

    r = client.post("/api/redo", data={"current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        parent = conn.execute(
            "SELECT kind FROM codebook_code WHERE id = ?",
            (code_a,),
        ).fetchone()
        child_after_redo = conn.execute(
            "SELECT deleted_at FROM codebook_code WHERE id = ?",
            (child["id"],),
        ).fetchone()
        ann_after_redo = conn.execute(
            "SELECT code_id FROM annotation WHERE id = ?",
            (ann_id,),
        ).fetchone()
    finally:
        conn.close()
    assert parent["kind"] == "folder"
    assert child_after_redo["deleted_at"] is None
    assert ann_after_redo["code_id"] == child["id"]


def test_reorder_in_scope_accepts_folder_rows(client_with_codes):
    """Nested folders require mixed code/folder sibling reorder in any scope."""
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder

    client, _coder, code_a, code_b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        fid = add_folder(conn, "Themes")
        before = conn.execute(
            "SELECT sort_order FROM codebook_code WHERE id = ?", (fid,)
        ).fetchone()["sort_order"]
    finally:
        conn.close()

    # Send the folder id at index 0. The mixed-scope route should honour it.
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([fid, code_a, code_b]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        after = conn.execute(
            "SELECT sort_order FROM codebook_code WHERE id = ?", (fid,)
        ).fetchone()["sort_order"]
    finally:
        conn.close()
    assert before != 0
    assert after == 0, "folder sort_order should be updated by reorder-in-scope"


def test_set_parent_route_respects_target_order(client_with_codes):
    """Cross-scope drag sends the destination sibling order with the parent move."""
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder

    client, _coder, _code_a, _code_b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        target_folder = add_folder(conn, "Target")
        first = _add_test_code(client, "First child", db_path, parent_id=target_folder)
        second = _add_test_code(client, "Second child", db_path, parent_id=target_folder)
        moving_folder = add_folder(conn, "Moving folder")
    finally:
        conn.close()
    before_colours = _code_colours(db_path, [first, second])

    response = client.put(
        f"/api/codes/{moving_folder}/parent",
        data={
            "parent_id": target_folder,
            "target_order_ids": json.dumps([first, moving_folder, second]),
            "current_index": 0,
        },
    )
    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"

    conn = open_project(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM codebook_code "
            "WHERE parent_id = ? AND deleted_at IS NULL "
            "ORDER BY sort_order",
            (target_folder,),
        ).fetchall()
    finally:
        conn.close()
    assert [row["id"] for row in rows] == [first, moving_folder, second]
    assert _code_colours(db_path, [first, second]) == before_colours

    response = client.post("/api/undo", data={"current_index": 0})
    assert response.status_code == 200

    conn = open_project(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM codebook_code "
            "WHERE parent_id = ? AND deleted_at IS NULL "
            "ORDER BY sort_order",
            (target_folder,),
        ).fetchall()
        parent_after_undo = conn.execute(
            "SELECT parent_id FROM codebook_code WHERE id = ?",
            (moving_folder,),
        ).fetchone()["parent_id"]
    finally:
        conn.close()
    assert [row["id"] for row in rows] == [first, second]
    assert parent_after_undo is None

    response = client.post("/api/redo", data={"current_index": 0})
    assert response.status_code == 200

    conn = open_project(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM codebook_code "
            "WHERE parent_id = ? AND deleted_at IS NULL "
            "ORDER BY sort_order",
            (target_folder,),
        ).fetchall()
    finally:
        conn.close()
    assert [row["id"] for row in rows] == [first, moving_folder, second]
