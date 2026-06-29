"""Tests for the coding page route."""

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




def test_coding_page_redirects_without_project():
    """GET /code without project redirects to /."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


def test_coding_page_redirects_without_coder(tmp_path):
    """GET /code without coder_id redirects to /."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        # coder_id not set
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


def test_coding_page_redirects_without_sources(tmp_path):
    """GET /code with no sources redirects to /import."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    coders = list_coders(conn)
    coder_id = coders[0]["id"]
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/import"


def test_coding_page_shows_source_content(client_with_sources):
    """First source text is visible in the text panel."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "First document content for coding." in resp.text


def test_coding_page_shows_codes(client_with_sources):
    """Codes appear in the sidebar."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "Theme A" in resp.text
    assert "Theme B" in resp.text
















def test_coding_page_uses_file_stem_in_title(client_with_sources):
    """The browser title uses the opened project filename."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "<title>Code — test — ACE</title>" in resp.text


def test_coding_page_title_uses_opened_file_stem_after_rename(tmp_path):
    """The browser title should follow the opened .ace filename."""
    app = create_app()
    original_path = tmp_path / "starter-project.ace"
    opened_path = tmp_path / "workshop-template.ace"
    conn = create_project(str(original_path), "Starter Project")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S001", "Text for coding.", "row")
    conn.close()
    original_path.rename(opened_path)

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(opened_path)
        app.state.coder_id = coder_id
        resp = client.get("/code")

    assert resp.status_code == 200
    assert "<title>Code — workshop-template — ACE</title>" in resp.text
    assert "<title>Code — Starter Project — ACE</title>" not in resp.text


def test_coding_page_index_param(client_with_sources):
    """Navigating to index=1 shows second source."""
    client, _ = client_with_sources
    resp = client.get("/code?index=1")
    assert resp.status_code == 200
    assert "Second document with different text." in resp.text


def test_coding_page_auto_creates_assignments(client_with_sources):
    """Assignments are auto-created for the coder."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    # Grid tile container + JSON payload should exist
    assert 'id="ace-grid-tiles"' in resp.text
    assert 'id="ace-sources-data"' in resp.text




def test_sidebar_strip_wordmark_links_home(client_with_sources):
    """Clicking the ACE wordmark returns to the landing page."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    body = resp.text
    # The wordmark anchor must point at "/" and carry the version in
    # its title (hover reveal). Asserts the masthead role too — the
    # strip is the page banner.
    assert 'class="ace-sidebar-strip" role="banner"' in body
    assert 'href="/" class="ace-sidebar-strip-mark"' in body
    assert 'title="ACE v' in body




def test_sidebar_has_headless_tree_mount(client_with_sources):
    """Sidebar exposes the headless tree mount; treeitems render client-side."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="ace-headless-tree-mount"' in html
    assert 'role="tree"' in html
    assert 'aria-label="Code list"' in html
    assert 'id="code-tree"' not in html


def test_sidebar_resize_handle_has_separator_accessibility_contract(client_with_sources):
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="resize-handle"' in html
    assert 'role="separator"' in html
    assert 'aria-orientation="vertical"' in html
    assert 'aria-label="Resize codebook sidebar"' in html
    assert 'aria-controls="code-sidebar"' in html
    assert 'aria-valuemin="150"' in html
    assert 'aria-valuenow="' in html
    assert 'tabindex="0"' in html


# ---------------------------------------------------------------------------
# Annotation CRUD routes
# ---------------------------------------------------------------------------










# ---------------------------------------------------------------------------
# Global /api/undo + /api/redo (Task 5)
# ---------------------------------------------------------------------------






















# ---------------------------------------------------------------------------
# Flag routes
# ---------------------------------------------------------------------------














# ---------------------------------------------------------------------------
# Grid cell pre-computation
# ---------------------------------------------------------------------------




def test_sidebar_grid_replaces_popover(client_with_codes):
    """Coding page renders the sparkline + tile grid, not the legacy overlay."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    resp = client.get("/code")
    body = resp.text

    # New markers present
    assert 'id="ace-sidebar-grid"' in body
    assert 'id="ace-grid-spark"' in body
    assert 'id="ace-grid-tiles"' in body
    assert 'id="ace-grid-inspector"' in body
    assert 'id="ace-sources-data"' in body

    # Legacy markers gone
    for gone in (
        "source-grid-overlay",
        "ace-grid-overlay",
        "ace-grid-popover",
        "aceToggleGrid",
        "ace-grid-cell--ann-1",
        "ace-grid-cell--ann-3",
        "ace-grid-cell--ann-6",
        "ace-grid-cell--complete",
    ):
        assert gone not in body, f"legacy marker {gone!r} still in response"


def test_grid_separator_aria(client_with_codes):
    """Resize separator has the full ARIA contract required by WAI-ARIA."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    assert 'class="ace-sidebar-vsplit"' in body
    required = [
        'role="separator"',
        'aria-orientation="horizontal"',
        'aria-controls="ace-sidebar-grid"',
        'aria-valuemin=',
        'aria-valuemax=',
        'aria-valuenow=',
        'aria-valuetext=',
        'tabindex="0"',
    ]
    for attr in required:
        assert attr in body, f"separator missing {attr!r}"




def test_grid_scaffold_and_live_region(client_with_codes):
    """Tile grid container + live region scaffold present on the coding page."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    # Live region wired up with the correct aria-live value
    assert 'id="ace-grid-live"' in body
    assert 'aria-live="polite"' in body

    # Tile grid host exists (tiles are rendered client-side)
    assert 'id="ace-grid-tiles"' in body
    assert 'role="grid"' in body

    # Sources payload present
    assert 'id="ace-sources-data"' in body








def test_coding_page_has_collapsible_grid_header(client_with_codes):
    """Source-grid header is a single button with chevron + 'Sources' label, no total count."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text

    # Collapsible button replaces the old header span pair
    assert 'id="ace-grid-collapse-btn"' in body
    assert 'aria-expanded="true"' in body
    assert 'class="ace-grid-header"' in body
    assert "ace-grid-chevron" in body
    # Title is now "Source map" using the shared panel-heading class,
    # and the button sits inside an <h2> (W3C accordion pattern) with
    # aria-labelledby on the section pointing at the visible heading.
    assert '<span id="ace-sidebar-grid-heading" class="ace-panel-heading">Source map</span>' in body
    # The button is wrapped in an h2 via the shared .ace-panel-heading-wrap utility
    assert '<h2 class="ace-panel-heading-wrap">' in body
    # Section landmark references the visible heading, not a redundant aria-label
    assert 'aria-labelledby="ace-sidebar-grid-heading"' in body
    # Total count no longer in header (it still appears in range label, which is
    # client-rendered)
    assert 'class="ace-grid-meta"' not in body
    # Wrapper for collapse state exists
    assert 'id="ace-grid-content"' in body


def test_coding_sidebar_renders_visible_codebook_legend(client_with_codes):
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    resp = client.get("/code?index=0")

    body = resp.text
    assert 'class="ace-sidebar-legend"' in body
    assert "Shift+Enter" in body
    assert "folder" in body
    assert "Opt" in body
    assert "move" in body
    assert "Cmd+X/V" in body


def test_coding_page_has_inline_collapse_restore_script(client_with_codes):
    """Inline head script restores ace-grid-collapsed dataset before CSS loads."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    assert 'localStorage.getItem("ace-grid-collapsed")' in body
    assert "dataset.aceGridCollapsed" in body




def test_oob_status_emits_statusbar_receipt_and_live_region_fragments():
    """_oob_status emits global fallback, coding receipt, and live region OOB fragments."""
    from ace.routes.api import _oob_status

    response = _oob_status("Validation failed", "err")
    body = response.body.decode("utf-8")

    assert 'id="ace-statusbar-event"' in body
    assert "ace-statusbar-event--err" in body

    assert 'id="ace-notification-receipt"' in body
    assert "ace-notification-receipt--err" in body
    assert 'id="ace-text-event-pill"' not in body

    assert body.count("Validation failed") >= 2
    assert 'id="ace-live-region-assertive"' in body
    assert 'role="alert"' in body


def test_oob_status_ok_kind_uses_ok_class_suffix():
    """_oob_status with kind='ok' uses --ok class suffix on global and receipt fragments."""
    from ace.routes.api import _oob_status

    response = _oob_status("Saved", "ok")
    body = response.body.decode("utf-8")
    assert "ace-statusbar-event--ok" in body
    assert "ace-notification-receipt--ok" in body
    assert 'id="ace-live-region"' in body


def test_oob_status_undo_emits_receipt_with_button_and_live_region():
    """_oob_status_undo emits the new receipt affordance while preserving the global fallback."""
    from ace.routes.api_support import _oob_status_undo

    body = _oob_status_undo("Removed code")

    assert 'id="ace-statusbar-event"' in body
    assert "ace-statusbar-event--undo" in body
    assert 'id="ace-notification-receipt"' in body
    assert "ace-notification-receipt--undo" in body
    receipt = body[body.index('id="ace-notification-receipt"'):body.index('data-ace-undo-affordance')]
    assert 'role="status"' not in receipt
    assert 'aria-live="polite"' not in receipt
    assert 'data-ace-undo-affordance="1"' in body
    assert 'aria-keyshortcuts="Z"' in body
    assert 'aria-label="Undo last action"' in body
    assert "Removed code" in body
    assert 'id="ace-live-region"' in body


# ---------------------------------------------------------------------------
# Merge-on-apply integration tests
# ---------------------------------------------------------------------------


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




def test_coding_page_has_page_title(client_with_codes):
    """/code renders a centred H1 'Coding' above the nav cluster."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    # H1 with the shared page-title class
    assert '<h1 class="ace-page-title' in body
    assert '>Coding</h1>' in body
    # H1 appears before the nav cluster in document order
    h1_pos = body.index('>Coding</h1>')
    nav_pos = body.index('ace-nav-cluster')
    assert h1_pos < nav_pos






# ---------------------------------------------------------------------------
# Folder + parent + cut-paste routes (Task 5)
# ---------------------------------------------------------------------------


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
























# ---------------------------------------------------------------------------
# Reorder-in-scope route (Task 11) — same-scope drag persists sort_order
# without recording an undo entry, and returns the unified text-panel + OOB
# sidebar shape so count chips stay consistent across the swap.
# ---------------------------------------------------------------------------


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


















# ---------------------------------------------------------------------------
# PR review fixes — F2 / F4 / F5 / F7
# ---------------------------------------------------------------------------


















# ---------------------------------------------------------------------------
# annotate_sentence — branch-specific status messages (#14)
# ---------------------------------------------------------------------------


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
