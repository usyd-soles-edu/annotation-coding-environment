"""Tests for the /code/{id}/view page route."""

import json
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


class _ElementFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _elements(body: str):
    parser = _ElementFinder()
    parser.feed(body)
    return parser.elements


def _attrs_by_id(body: str, element_id: str) -> dict[str, str]:
    for _tag, attrs in _elements(body):
        if attrs.get("id") == element_id:
            return attrs
    raise AssertionError(f"missing element id={element_id!r}")


@pytest.fixture()
def client_with_annotations(tmp_path):
    """Project with 2 sources, 1 code, and 3 annotations."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coder_id = list_coders(conn)[0]["id"]
    s1 = add_source(conn, "S001", "a" * 100, "row")
    s2 = add_source(conn, "S002", "b" * 200, "row")
    code = add_code(conn, "Theme A", "#1565c0")

    add_annotation(conn, s1, coder_id, code, 0, 10, "aaaaaaaaaa")
    add_annotation(conn, s1, coder_id, code, 30, 40, "aaaaaaaaaa")
    add_annotation(conn, s2, coder_id, code, 50, 75, "b" * 25)
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")  # auto-create assignments
        yield client, coder_id, code, str(db_path)


def test_view_happy_path(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert "Theme A" in resp.text
    assert 'id="ace-codeview-data"' in resp.text


def test_audit_sidebar_declares_audit_mode(client_with_annotations):
    """Code sidebar renders with explicit audit mode in coded text view."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert 'data-codebook-mode="audit"' in resp.text
    assert "Arrows view codes" in resp.text
    assert "Enter renames" in resp.text
    assert "Press Enter to apply" not in resp.text
    assert 'id="ace-code-create-actions"' in resp.text


def test_view_data_blob_is_valid_json(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    m = re.search(
        r'<script id="ace-codeview-data" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    assert m, "ace-codeview-data script not found"
    data = json.loads(m.group(1))
    assert data["code"]["name"] == "Theme A"
    assert data["stats"]["excerpts"] == 3
    assert data["stats"]["sources_with_hits"] == 2
    assert data["stats"]["total_sources"] == 2
    assert len(data["sources"]) == 2


def test_view_redirects_when_no_project(tmp_path):
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/code/any-id/view", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/"


def test_view_redirects_when_no_coder(tmp_path):
    app = create_app()
    db_path = tmp_path / "test.ace"
    create_project(str(db_path), "Test")
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        # No coder_id set
        resp = client.get("/code/any-id/view", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/"


def test_view_redirects_when_unknown_code(client_with_annotations):
    client, _, _, _ = client_with_annotations
    resp = client.get("/code/does-not-exist/view", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/code"


def test_view_page_shares_sidebar_strip_with_code_page(client_with_annotations):
    """Coded-text-view shares the sidebar strip masthead with /code.

    Guards against someone inlining the shared sidebar partial on only
    one of the two routes that render it.
    """
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    body = resp.text
    assert 'class="ace-sidebar-strip"' in body
    assert 'class="ace-sidebar-strip-mark"' in body
    assert ">ACE</a>" in body


def test_code_view_has_column_headings(client_with_annotations):
    """Coded-text view shows visible H2 headings on both columns,
    and each section uses aria-labelledby to point at its visible heading."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    body = resp.text

    # Visible column headings
    assert '<h2 id="cv-tracks-heading" class="ace-panel-heading">Sources</h2>' in body
    assert '<h2 id="cv-excerpts-heading" class="ace-panel-heading">Excerpts</h2>' in body

    # Sections point at the visible headings rather than carrying redundant aria-label
    assert 'class="cv-tracks-col" aria-labelledby="cv-tracks-heading"' in body
    assert 'class="cv-excerpts-col" aria-labelledby="cv-excerpts-heading"' in body

    # Document order: tracks heading inside tracks column; excerpts heading inside excerpts column
    tracks_col_pos = body.index('class="cv-tracks-col"')
    tracks_h2_pos = body.index('Sources</h2>')
    excerpts_col_pos = body.index('class="cv-excerpts-col"')
    excerpts_h2_pos = body.index('Excerpts</h2>')
    assert tracks_col_pos < tracks_h2_pos < excerpts_col_pos < excerpts_h2_pos


def test_code_view_has_desktop_review_edit_editor_shell(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    body = resp.text

    assert 'id="ace-notification-receipt"' in body
    assert 'class="ace-notification-receipt cv-notification-receipt"' in body
    assert 'aria-label="Review or edit this code"' in body
    assert 'id="cv-mode-review"' in body
    assert 'id="cv-mode-edit"' in body
    assert 'id="cv-source-review"' in body
    assert "data-cv-review-panel" in body
    assert 'id="cv-code-editor"' in body
    assert "data-cv-edit-panel" in body
    assert 'id="cv-code-name"' in body
    assert 'id="cv-code-folder"' in body
    assert 'id="cv-code-definition"' in body
    assert 'aria-keyshortcuts="Enter Meta+Enter Control+Enter"' in body
    assert 'aria-keyshortcuts="Meta+Enter Control+Enter"' in body


def test_code_view_uses_prominent_audit_mode_band(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    body = resp.text

    assert 'class="cv-mode-band" aria-label="Audit task mode"' in body
    assert 'id="cv-mode-title"' in body
    assert 'id="cv-mode-description"' in body
    assert 'id="cv-mode-status"' in body
    assert 'Review coded excerpts' in body
    assert "Coded excerpts are visible for audit and comparison." in body
    assert 'aria-label="Review or edit this code"' in body
    assert 'aria-label="Review/Edit mode"' not in body

    review_attrs = _attrs_by_id(body, "cv-mode-review")
    assert review_attrs["type"] == "button"
    assert review_attrs["aria-pressed"] == "true"
    assert review_attrs["aria-controls"] == "cv-source-review"
    assert ">Review excerpts</button>" in body

    edit_attrs = _attrs_by_id(body, "cv-mode-edit")
    assert edit_attrs["type"] == "button"
    assert edit_attrs["aria-pressed"] == "false"
    assert edit_attrs["aria-controls"] == "cv-code-editor"
    assert ">Edit code details</button>" in body

    header_pos = body.index('class="cv-header"')
    band_pos = body.index('class="cv-mode-band"')
    body_pos = body.index('class="cv-body"')
    assert header_pos < band_pos < body_pos


def test_cv_table_has_listbox_role(client_with_annotations):
    """Excerpts container is a listbox so roving tabindex + arrow keys
    announce correctly to AT."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert 'id="cv-table"' in resp.text
    assert 'role="listbox"' in resp.text
    # Confirm the role belongs to #cv-table, not just #cv-tracks
    # (search for role on the cv-table element specifically)
    m = re.search(r'<div[^>]*\bid="cv-table"[^>]*>', resp.text)
    assert m is not None, "cv-table div not found"
    assert 'role="listbox"' in m.group(0), \
        f"role=listbox not on cv-table div: {m.group(0)}"


def test_cv_tracks_has_listbox_role_regression(client_with_annotations):
    """Sources listbox — regression guard. Already present pre-change."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    # Confirm role + aria-multiselectable belong to #cv-tracks specifically,
    # not just any element in the response.
    m = re.search(r'<div[^>]*\bid="cv-tracks"[^>]*>', resp.text)
    assert m is not None, "cv-tracks div not found"
    assert 'role="listbox"' in m.group(0), \
        f"role=listbox not on cv-tracks div: {m.group(0)}"
    assert 'aria-multiselectable="true"' in m.group(0), \
        f'aria-multiselectable="true" not on cv-tracks div: {m.group(0)}'


def test_codebook_search_has_slash_keyshortcut_regression(client_with_annotations):
    """Codebook search input advertises `/` hotkey — regression guard.
    Already present via _sidebar_codebook.html pre-change."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert 'id="code-search-input"' in resp.text
    assert 'aria-keyshortcuts="/ Enter Shift+Enter Escape"' in resp.text


def test_code_view_has_cheatsheet_dialog(client_with_annotations):
    """`?` cheat sheet dialog is rendered server-side for /view with shortcut content."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    # Extract the dialog block so the shortcut assertions don't get fooled by
    # matches elsewhere on the page (e.g. "Tab" appearing in unrelated copy).
    m = re.search(
        r'<dialog[^>]*id="cv-cheatsheet-dialog".*?</dialog>',
        resp.text,
        re.DOTALL,
    )
    assert m is not None, "cheatsheet dialog block not found"
    dialog = m.group(0)
    assert "Coded text shortcuts" in dialog
    # Every zone gets its own section — guard against an empty/truncated body.
    assert "Move between columns" in dialog
    assert "Move cursor" in dialog
    assert "pin / unpin" in dialog.lower()


class TestViewDataJsonEndpoint:
    def test_happy_path_returns_view_data_dict(self, client_with_annotations):
        client, _, code_id, _ = client_with_annotations
        resp = client.get(f"/api/code/{code_id}/view-data")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert data["code"]["name"] == "Theme A"
        assert data["stats"]["excerpts"] == 3
        assert data["stats"]["sources_with_hits"] == 2
        assert data["stats"]["total_sources"] == 2
        assert len(data["sources"]) == 2

    def test_unknown_code_returns_404(self, client_with_annotations):
        client, *_ = client_with_annotations
        resp = client.get("/api/code/does-not-exist/view-data")
        assert resp.status_code == 404

    def test_no_coder_returns_400(self, tmp_path):
        app = create_app()
        db_path = tmp_path / "noc.ace"
        create_project(str(db_path), "P").close()
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.project_path = str(db_path)
            # deliberately no coder_id set
            resp = client.get("/api/code/anything/view-data")
            assert resp.status_code == 400

    def test_no_project_redirects(self, tmp_path):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/code/anything/view-data", follow_redirects=False)
            assert resp.status_code == 302
