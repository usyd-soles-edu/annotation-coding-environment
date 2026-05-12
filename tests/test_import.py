"""Tests for the import page and API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project


@pytest.fixture()
def client_with_project(tmp_path):
    """Create a .ace project, set app state, return (client, tmp_path)."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        yield client, tmp_path


def test_import_page_renders(client_with_project):
    """GET /import shows import page."""
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "What would you like to import" in resp.text


def test_import_page_uses_hidden_steps_and_live_message(client_with_project):
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert 'id="import-message"' in resp.text
    assert 'class="ace-wizard-title"' in resp.text
    assert 'id="step-upload" hidden' in resp.text
    assert 'id="step-folder" hidden' in resp.text
    assert 'id="step-columns" hidden' in resp.text
    assert 'id="step-done" hidden' in resp.text


def test_import_page_file_picker_has_keyboard_button(client_with_project):
    client, _ = client_with_project
    resp = client.get("/import")
    assert 'id="import-file-button"' in resp.text
    assert 'type="button"' in resp.text
    assert 'id="import-file-input"' in resp.text
    assert 'id="import-file-input" class="ace-sr-only" tabindex="-1"' in resp.text
    assert 'aria-label="Import file"' in resp.text
    assert 'style="display:none"' not in resp.text


def test_upload_csv_shows_preview(client_with_project):
    """Upload CSV returns preview table with column selection."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "participant_id,reflection,age\n"
        "P001,I enjoyed the group work.,22\n"
        "P002,The lectures were fast.,25\n"
    )

    with open(csv_path, "rb") as f:
        resp = client.post(
            "/api/import/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )

    assert resp.status_code == 200
    assert "ace-glimpse" in resp.text
    assert "P001" in resp.text
    assert "participant_id" in resp.text
    assert '<h1 class="ace-wizard-title" tabindex="-1">Select columns</h1>' in resp.text
    assert '<p class="ace-wizard-q">Select columns</p>' not in resp.text
    assert "Choose one ID column and at least one Text column." in resp.text
    assert 'class="ace-glimpse-row" data-col="participant_id" data-role="" tabindex="0"' not in resp.text
    assert 'class="ace-role-btn" data-role="id" aria-pressed="false"' in resp.text
    assert 'class="ace-role-btn" data-role="text" aria-pressed="false"' in resp.text
    # Should have inline role toggle buttons
    assert "ace-role-btn" in resp.text
    assert 'data-role="id"' in resp.text
    assert 'data-role="text"' in resp.text


def test_import_commit(client_with_project):
    """Import with selected columns creates sources."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text,group\nA1,hello,ctrl\nA2,world,exp\n")

    # Upload first to set the temp path
    with open(csv_path, "rb") as f:
        client.post(
            "/api/import/upload",
            files={"file": ("data.csv", f, "text/csv")},
        )

    # Commit the import
    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": "text"},
    )

    assert resp.status_code == 200
    assert "2 sources" in resp.text
    assert '<h1 class="ace-wizard-count" tabindex="-1">2 sources</h1>' in resp.text
    assert "Start coding" in resp.text


def test_import_preview_returns_snippet(client_with_project):
    """GET /api/import/preview returns a file-browser preview fragment."""
    client, tmp_path = client_with_project

    folder = tmp_path / "prev"
    folder.mkdir()
    (folder / "doc.txt").write_text("Preview content here.")

    resp = client.get("/api/import/preview", params={"folder": str(folder)})
    assert resp.status_code == 200
    assert 'id="import-preview"' in resp.text
    assert "ace-folder-import-browser" in resp.text
    assert "Random sample" in resp.text
    assert "Previewing" in resp.text
    assert "doc.txt" in resp.text
    assert "Preview content here." in resp.text
    assert "Showing 1 of 1" in resp.text
    assert 'title="Show another random sample"' in resp.text
    assert 'aria-label="Show another random sample"' in resp.text


def test_import_preview_shows_five_file_sample(client_with_project):
    """Folder preview lists a random sample of five files, not every file."""
    client, tmp_path = client_with_project

    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(7):
        (folder / f"doc-{i}.txt").write_text(f"Preview content {i}.")

    resp = client.get("/api/import/preview", params={"folder": str(folder)})

    assert resp.status_code == 200
    assert resp.text.count("data-import-preview-file") == 5
    assert "Showing 5 of 7" in resp.text
    assert "2 more files imported" in resp.text


def test_import_preview_empty_folder(client_with_project):
    """GET /api/import/preview with empty folder returns fallback."""
    client, tmp_path = client_with_project

    folder = tmp_path / "empty"
    folder.mkdir()

    resp = client.get("/api/import/preview", params={"folder": str(folder)})
    assert resp.status_code == 200
    assert "No text files" in resp.text


def test_import_page_has_consistent_buttons(client_with_project):
    """Both import options use ace-wizard-option buttons, no dropzone."""
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "ace-wizard-dropzone" not in resp.text
    assert "ace-wizard-option" in resp.text


def test_import_folder(client_with_project):
    """Import .txt folder creates sources and shows preview."""
    client, tmp_path = client_with_project

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document")
    (folder / "two.txt").write_text("Second document")

    resp = client.post(
        "/api/import/folder",
        data={"path": str(folder)},
    )

    assert resp.status_code == 200
    assert "2 text files" in resp.text
    assert '<h1 class="ace-wizard-count" tabindex="-1">2 text files</h1>' in resp.text
    assert "Start coding" in resp.text
    assert "Import more data" in resp.text
    assert "ace-folder-import-browser" in resp.text
    assert "Random sample" in resp.text
    assert "Previewing" in resp.text
