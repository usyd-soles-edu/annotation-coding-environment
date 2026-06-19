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


def test_sidebar_has_brand_and_nav_has_source(client_with_sources):
    """Sidebar shows the ACE wordmark strip, nav shows flag button."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="ace-sidebar-strip"' in html
    assert 'class="ace-sidebar-strip-mark"' in html
    assert ">ACE</a>" in html
    assert 'aria-label="Toggle flag (Shift+F)"' in html


def test_annotate(client_with_codes):
    """POST /api/code/apply creates annotation and returns updated HTML."""
    client, coder_id, code_a, _, db_path = client_with_codes
    resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert resp.status_code == 200
    # Annotation routes return OOB-only responses with HX-Reswap: none —
    # bridge.js refreshes highlights inside the existing #text-panel
    # without a primary swap, so the response carries no text-panel HTML.
    assert resp.headers.get("HX-Reswap") == "none"
    assert "text-panel" not in resp.text
    # OOB blobs that drive the in-place client-side update.
    assert 'id="ace-ann-data"' in resp.text
    assert 'id="ace-applied-codes-panel"' in resp.text

    # Verify annotation exists in the DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["selected_text"] == "First"


def test_delete_annotation(client_with_codes):
    """POST /api/code/delete-annotation soft-deletes an annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # First create an annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Get the annotation ID
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ann = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()
    ann_id = ann["id"]
    conn.close()

    # Delete it
    resp = client.post(
        "/api/code/delete-annotation",
        data={"annotation_id": ann_id, "current_index": 0},
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Reswap") == "none"
    assert "text-panel" not in resp.text

    # Verify soft-deleted in DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    deleted = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NOT NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 0
    assert len(deleted) == 1


def test_undo_after_annotate(client_with_codes):
    """Undo reverses the last annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Undo
    resp = client.post(
        "/api/undo",
        data={"current_index": 0},
    )
    assert resp.status_code == 200
    assert 'id="code-sidebar"' not in resp.text

    # Verify annotation is now soft-deleted
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 0


def test_redo_after_undo(client_with_codes):
    """Redo restores the undone annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Undo
    client.post("/api/undo", data={"current_index": 0})

    # Redo
    resp = client.post("/api/redo", data={"current_index": 0})
    assert resp.status_code == 200

    # Verify annotation is active again
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 1
    assert active[0]["selected_text"] == "First"


def test_undo_endpoint_pops_undo_stack(client_with_codes):
    """POST /api/undo runs the inverse mutation and returns 200 with OOB swap."""
    client, _coder_id, code_id, _, _db_path = client_with_codes
    # Apply a code to source 0 — record_add fires automatically inside the route
    resp = client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    assert resp.status_code == 200

    # Now undo
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    # Status bar OOB present
    assert 'id="ace-statusbar-event"' in resp.text
    assert "Undone:" in resp.text


def test_undo_endpoint_empty_stack_returns_status(client_with_codes):
    """POST /api/undo on empty stack returns 'Nothing to undo' AND signals the
    client not to perform a primary swap. Without HX-Reswap=none, HTMX would
    receive an OOB-only response and replace #text-panel with empty content.
    """
    client, _coder_id, _code_id, _, _db_path = client_with_codes
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to undo" in resp.text
    assert resp.headers.get("HX-Reswap") == "none"

    resp = client.post("/api/redo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to redo" in resp.text
    assert resp.headers.get("HX-Reswap") == "none"


def test_old_code_undo_endpoint_removed(client_with_codes):
    """POST /api/code/undo no longer exists."""
    client, _coder_id, _code_id, _, _db_path = client_with_codes
    resp = client.post("/api/code/undo", data={"current_index": 0})
    assert resp.status_code == 404


def test_undo_annotation_delete_includes_flash_script(client_with_codes):
    """Undoing an annotation_delete returns a flash OOB script targeting #ace-undo-flash.

    Locks the wire so future changes to the flash plumbing don't silently regress.
    HTMX 2.x silently drops OOB swaps whose target is missing, so this also
    indirectly guards the placeholder in coding.html.
    """
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply a code, then look up its annotation id
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    ann_id = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()["id"]
    conn.close()

    # Delete the annotation (records annotation_delete on the undo stack)
    client.post("/api/code/delete-annotation", data={
        "annotation_id": ann_id, "current_index": 0,
    })

    # Undo the delete — response should include the flash OOB script
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert 'id="ace-undo-flash"' in resp.text
    assert 'hx-swap-oob="outerHTML"' in resp.text
    assert "_flashAnnotation" in resp.text
    assert ann_id in resp.text


def test_undo_cross_source_includes_navigate_trigger(client_with_codes):
    """Undo of an annotation made on a different source emits HX-Trigger: ace-navigate."""
    import json as _json

    client, _coder_id, code_id, _, _db_path = client_with_codes

    # Apply on source 0
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })

    # Undo from source 1 (different) — fixture has 2 sources, so index 1 is the
    # "other" source the user has navigated to.
    resp = client.post("/api/undo", data={"current_index": 1})
    assert resp.status_code == 200
    trigger = resp.headers.get("HX-Trigger", "")
    assert "ace-navigate" in trigger
    data = _json.loads(trigger)
    assert data["ace-navigate"]["index"] == 0


def test_flag_source(client_with_sources):
    """POST /api/code/flag toggles the flagged status."""
    client, _ = client_with_sources
    # Visit /code first so assignments are auto-created
    client.get("/code")

    # Flag source 0
    resp = client.post(
        "/api/code/flag",
        data={"source_index": "0"},
    )
    assert resp.status_code == 200
    assert "flagged" in resp.text.lower()

    # Flag again to unflag
    resp = client.post(
        "/api/code/flag",
        data={"source_index": "0"},
    )
    assert resp.status_code == 200


def test_flag_source_toggle_roundtrip(client_with_codes):
    """Flagging twice returns to unflagged."""
    client, coder_id, _, _, db_path = client_with_codes

    # Flag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["flagged"] == 1
    conn.close()

    # Unflag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["flagged"] == 0
    conn.close()


def test_undo_does_not_set_x_ace_toast_and_announces_via_live_region(client_with_codes):
    """Undo action announces to the polite live region (and the status bar 'ok' channel)."""
    client, _coder_id, code_a, _code_b, _db_path = client_with_codes
    # Create an annotation we can undo
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "X-ACE-Toast" not in resp.headers
    assert 'id="ace-live-region"' in resp.text
    # The new global undo emits a "Undone: ..." description that includes
    # the code name and source display id.
    assert "Undone:" in resp.text
    assert "Theme A" in resp.text


def test_flag_does_not_set_x_ace_toast_and_announces_via_live_region(client_with_codes):
    """Flag action is silent in the status bar but announces to the polite live region."""
    client, _coder_id, _code_a, _code_b, _db_path = client_with_codes
    resp = client.post("/api/code/flag", data={"source_index": "0"})
    assert resp.status_code == 200
    assert "X-ACE-Toast" not in resp.headers
    assert 'id="ace-live-region"' in resp.text
    assert "Source flagged" in resp.text


def test_counter_chip_is_static(client_with_codes):
    """Counter span stays visible but has no onclick or ⚇ glyph."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    # Static text still present in flag row
    assert 'class="ace-nav-counter"' in body
    # Clickable affordance gone
    assert "aceToggleGrid" not in body
    assert "\u2687" not in body


def test_annotate_refreshes_grid(client_with_codes):
    """POST /api/code/apply returns OOB sources blob with incremented count."""
    import json
    import re
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert resp.status_code == 200
    # Annotation apply omits the sidebar OOB — counts are patched client-side.
    assert 'id="code-sidebar"' not in resp.text
    assert 'id="ace-sources-data"' in resp.text

    # Parse the OOB blob and confirm the first source now has count == 1.
    # The OOB payload is JSON with < > & escaped as \u003c \u003e \u0026 (Task 4 fix);
    # those are valid inside JSON strings so json.loads accepts it as-is.
    m = re.search(
        r'id="ace-sources-data"[^>]*hx-swap-oob[^>]*>([^<]*)</script>',
        resp.text,
    )
    assert m, "ace-sources-data OOB fragment not found in response"
    payload = json.loads(m.group(1))
    assert payload[0]["count"] == 1


def test_delete_refreshes_grid(client_with_codes):
    """Deleting an annotation returns OOB sources blob with decremented count."""
    import json
    import re
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    # Create an annotation, then delete it
    create = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert create.status_code == 200

    # Pull the new annotation id from the ann-data OOB blob (data-annotations attr)
    m = re.search(r'data-annotations="([^"]+)"', create.text)
    assert m, "ann-data payload missing from create response"
    payload = m.group(1).replace("&#34;", '"').replace("&quot;", '"')
    anns = json.loads(payload)
    assert anns, "ann-data was empty after apply"
    ann_id = anns[0]["id"]

    # Delete the annotation
    resp = client.post(
        "/api/code/delete-annotation",
        data={
            "annotation_id": ann_id,
            "current_index": 0,
        },
    )
    assert resp.status_code == 200, (
        f"delete returned {resp.status_code}: {resp.text[:200]}"
    )
    # Annotation delete omits the sidebar OOB — counts are patched client-side.
    assert 'id="code-sidebar"' not in resp.text
    assert 'id="ace-sources-data"' in resp.text

    # Parse the OOB sources blob — source 0's count should be back to 0
    m = re.search(
        r'id="ace-sources-data"[^>]*hx-swap-oob[^>]*>([^<]*)</script>',
        resp.text,
    )
    assert m, "ace-sources-data OOB fragment missing after delete"
    sources = json.loads(m.group(1))
    assert sources[0]["count"] == 0


def test_coding_page_text_header_has_three_rows(client_with_sources):
    """Text panel header is wrapped in .ace-text-header with nav, event row, flag row in that order."""
    client, _ = client_with_sources
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text

    # Wrapper present
    assert 'class="ace-text-header"' in body
    # Three child rows — ordering matters
    nav_idx = body.find('class="ace-text-nav"')
    event_idx = body.find('class="ace-text-event-row"')
    flag_idx = body.find('class="ace-flag-row"')
    assert nav_idx > 0 and event_idx > 0 and flag_idx > 0
    assert nav_idx < event_idx < flag_idx

    # Event pill element present, empty on initial render
    assert 'id="ace-text-event-pill"' in body
    assert 'class="ace-text-event-pill"' in body
    assert 'role="status"' in body
    assert 'aria-live="polite"' in body


def test_apply_same_code_overlap_merges(client_with_codes):
    """POST /api/code/apply twice with overlapping same-code ranges → 1 annotation."""
    client, _, code_a, _, db_path = client_with_codes

    r1 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    assert r1.status_code == 200

    r2 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })
    assert r2.status_code == 200

    assert _count_active_annotations(client, db_path, 0) == 1


def test_apply_status_applied_for_new_selection(client_with_codes):
    """POST /api/code/apply emits an 'Applied <code>' OOB status for a new span."""
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    resp = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    assert resp.status_code == 200
    body = resp.text
    # OOB status fragments present with the ok kind…
    assert 'id="ace-statusbar-event"' in body
    assert "ace-statusbar-event--ok" in body
    assert "ace-text-event-pill--ok" in body
    # …and the message names the applied code (code_a's name is "Theme A").
    assert "Applied Theme A" in body


def test_apply_status_merged_for_adjacent_same_code(client_with_codes):
    """Re-applying the same code to an overlapping span emits a 'Merged' status."""
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    # First apply — a fresh span → Applied.
    r1 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    assert r1.status_code == 200
    assert "Applied Theme A" in r1.text

    # Second apply, overlapping the first → merged into one spanning row.
    r2 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })
    assert r2.status_code == 200
    body = r2.text
    assert "Merged Theme A with adjacent" in body
    assert "ace-statusbar-event--ok" in body


def test_apply_different_code_overlap_creates_two(client_with_codes):
    """Overlap with DIFFERENT code → both annotations remain."""
    client, _, code_a, code_b, db_path = client_with_codes

    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    client.post("/api/code/apply", data={
        "code_id": code_b, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })

    assert _count_active_annotations(client, db_path, 0) == 2


def test_apply_merge_then_undo_restores_originals(client_with_codes):
    """After a merge, undo: originals restored, merged one gone."""
    client, _, code_a, _, db_path = client_with_codes

    # Two non-overlapping annotations first
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 4, "selected_text": "Firs",
    })
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 10, "end_offset": 14, "selected_text": "cont",
    })
    assert _count_active_annotations(client, db_path, 0) == 2

    # Spanning apply merges both
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 2, "end_offset": 13, "selected_text": "rst documen",
    })
    assert _count_active_annotations(client, db_path, 0) == 1

    # Undo → originals restored
    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert _count_active_annotations(client, db_path, 0) == 2


def test_apply_merge_then_undo_then_redo(client_with_codes):
    """Undo + redo returns to merged state. Asserts specific ranges to prove
    the right annotation survives each transition (count alone would pass even
    if undo/redo were no-ops)."""
    client, _, code_a, _, db_path = client_with_codes

    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })
    assert _active_annotation_ranges(db_path, 0) == [(0, 15)]

    client.post("/api/undo", data={"current_index": 0})
    assert _active_annotation_ranges(db_path, 0) == [(0, 10)]

    client.post("/api/redo", data={"current_index": 0})
    assert _active_annotation_ranges(db_path, 0) == [(0, 15)]


def test_applied_codes_panel_empty_state(client_with_codes):
    """Applied-codes inspector renders an empty state before any source codes exist."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    body = r.text
    assert 'id="ace-applied-codes-panel"' in body
    assert 'No codes applied to this source.' in body
    assert 'class="ace-applied-code-row"' not in body


def test_applied_codes_panel_when_present(client_with_codes):
    """Applied-codes inspector shows the source-position timeline and code rows."""
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    # Apply one code to source 0
    apply_resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert apply_resp.status_code == 200
    r = client.get("/code?index=0")
    body = r.text
    assert 'id="ace-applied-codes-panel"' in body
    assert 'class="ace-applied-code-row"' in body
    assert 'class="ace-applied-timeline-marker"' in body
    assert 'Code positions in source' in body
    # Title appears before the first row
    title_pos = body.index('Applied codes</span>')
    row_pos = body.index('class="ace-applied-code-row"')
    assert title_pos < row_pos


def test_annotate_sentence_add_status(client_with_codes):
    """POST /api/code/apply-sentence (new code) -> 'Applied' status fragment."""
    client, _coder_id, code_a, _code_b, _db_path = client_with_codes
    resp = client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 0, "current_index": 0},
    )
    assert resp.status_code == 200
    assert "Applied" in resp.text
    assert "Theme A" in resp.text
    # The status fragment swaps into the event channel.
    assert 'id="ace-statusbar-event"' in resp.text
    assert "ace-statusbar-event--ok" in resp.text


def test_annotate_sentence_toggle_off_status(client_with_codes):
    """Applying the same code to the same sentence again -> 'Removed' status."""
    client, _coder_id, code_a, _code_b, _db_path = client_with_codes
    # First apply (add)
    client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 0, "current_index": 0},
    )
    # Second apply (toggle off)
    resp = client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 0, "current_index": 0},
    )
    assert resp.status_code == 200
    assert "Removed" in resp.text
    assert "Theme A" in resp.text
    assert 'id="ace-statusbar-event"' in resp.text


def test_annotate_sentence_merge_status(client_with_two_sentences):
    """Applying a code to a sentence adjacent to an existing same-code span
    -> 'Merged with adjacent' status."""
    client, _coder_id, code_a, _db_path = client_with_two_sentences
    # Apply to sentence 0 (add)
    client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 0, "current_index": 0},
    )
    # Apply same code to the adjacent sentence 1 (merge)
    resp = client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 1, "current_index": 0},
    )
    assert resp.status_code == 200
    assert "Merged" in resp.text
    assert "adjacent" in resp.text
    assert 'id="ace-statusbar-event"' in resp.text


def test_undo_after_annotate_sentence_merge_restores_original_sentence(
    client_with_two_sentences,
):
    """Undoing an adjacent sentence merge keeps the original sentence annotation."""
    client, _coder_id, code_a, db_path = client_with_two_sentences
    client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 0, "current_index": 0},
    )
    original = _active_annotation_ranges(db_path, 0)

    client.post(
        "/api/code/apply-sentence",
        data={"code_id": code_a, "sentence_index": 1, "current_index": 0},
    )
    assert _active_annotation_ranges(db_path, 0) != original

    resp = client.post("/api/undo", data={"current_index": 0})

    assert resp.status_code == 200
    assert _active_annotation_ranges(db_path, 0) == original
