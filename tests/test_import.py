"""Tests for the import page and API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project, open_project
from ace.models.source import get_source_content, list_sources


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
    assert "Choose your source data" in resp.text
    assert "Import a spreadsheet" in resp.text
    assert "Import a folder" in resp.text
    assert 'class="ace-route-list"' in resp.text
    assert resp.text.count("ace-route-row") == 2


def test_import_page_uses_hidden_steps_and_live_message(client_with_project):
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert 'id="import-message"' in resp.text
    assert 'class="ace-wizard-title"' in resp.text
    assert 'id="step-columns" hidden' in resp.text
    assert 'id="step-done" hidden' in resp.text
    assert 'id="step-folder"' not in resp.text


def test_import_page_spreadsheet_choice_uses_native_picker(client_with_project):
    client, _ = client_with_project
    resp = client.get("/import")
    assert 'id="import-spreadsheet-button"' in resp.text
    assert 'onclick="pickAndImportFile()"' in resp.text
    assert 'onclick="pickAndImportFolder()"' in resp.text
    assert "Browse for folder" not in resp.text
    assert 'id="step-upload"' not in resp.text
    assert 'id="import-file-input"' not in resp.text


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
    assert "ace-import-mapping" in resp.text
    assert "P001" in resp.text
    assert "participant_id" in resp.text
    assert '<h1 class="ace-wizard-title" tabindex="-1">Choose source labels and coding text</h1>' in resp.text
    assert "1. Source label" in resp.text
    assert "2. Text to code" in resp.text
    assert "Preview source" in resp.text
    assert "ace-role-btn" not in resp.text
    assert 'name="id_column_choice"' in resp.text
    assert "data-import-text-col" in resp.text


def test_import_file_path_shows_three_column_mapping(client_with_project):
    client, tmp_path = client_with_project
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "student_id,reflection,feedback,age\n"
        "S103,Reflection text,Feedback text,22\n"
        "S104,Second reflection,Second feedback,23\n"
    )

    resp = client.post("/api/import/file", data={"path": str(csv_path)})

    assert resp.status_code == 200
    assert "ace-import-mapping" in resp.text
    assert "1. Source label" in resp.text
    assert "2. Text to code" in resp.text
    assert "Preview source" in resp.text
    assert "Source label" in resp.text
    assert "S103" in resp.text
    assert "reflection" in resp.text
    assert "feedback" in resp.text
    assert 'aria-label="Show another random source"' in resp.text
    assert "&#x21BB;" in resp.text


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
    assert "ace-import-result" in resp.text
    assert "Import complete" in resp.text
    assert '<div class="ace-import-result-count">2 sources</div>' in resp.text
    assert "Start coding" in resp.text


def test_import_commit_requires_text_column(client_with_project):
    """Submitting without a text column does not create empty sources."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n", encoding="utf-8")

    with open(csv_path, "rb") as f:
        client.post(
            "/api/import/upload",
            files={"file": ("data.csv", f, "text/csv")},
        )

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": ""},
    )

    assert resp.status_code == 200
    assert "Choose at least one text column." in resp.text
    conn = open_project(tmp_path / "test.ace")
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()


def test_import_commit_multiple_text_columns_creates_one_source_per_row(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text(
        "id,reflection,feedback,group\n"
        "A1,Reflection one,Feedback one,ctrl\n"
        "A2,Reflection two,Feedback two,exp\n"
    )

    with open(csv_path, "rb") as f:
        client.post(
            "/api/import/upload",
            files={"file": ("data.csv", f, "text/csv")},
        )

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": "reflection,feedback"},
    )

    assert resp.status_code == 200
    assert "2 sources" in resp.text
    conn = open_project(tmp_path / "test.ace")
    try:
        sources = list_sources(conn)
        assert [source["display_id"] for source in sources] == ["A1", "A2"]
        assert sources[0]["source_column"] is None
        content = get_source_content(conn, sources[0]["id"])["content_text"]
        assert "reflection" in content
        assert "Reflection one" in content
        assert "feedback" in content
        assert "Feedback one" in content
    finally:
        conn.close()


def test_import_commit_keeps_native_file_path(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "native.csv"
    csv_path.write_text("id,text\nA1,hello\n")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": "text"},
    )

    assert resp.status_code == 200
    assert csv_path.exists()


def test_import_preview_returns_snippet(client_with_project):
    """GET /api/import/preview returns a file-browser preview fragment."""
    client, tmp_path = client_with_project

    folder = tmp_path / "prev"
    folder.mkdir()
    (folder / "doc.txt").write_text(
        "Preview content here.\nSecond line.", encoding="utf-8"
    )

    resp = client.get("/api/import/preview", params={"folder": str(folder)})
    assert resp.status_code == 200
    assert 'id="import-preview"' in resp.text
    assert "ace-folder-import-browser" in resp.text
    assert "data-preview-json=" in resp.text
    assert "Preview content here.\\nSecond line." in resp.text
    assert "Random sample" in resp.text
    assert "Previewing" in resp.text
    assert "doc.txt" in resp.text
    assert "Preview content here." in resp.text
    assert "Showing 1 of 1" in resp.text
    assert 'title="Preview another file"' in resp.text
    assert 'aria-label="Preview another file"' in resp.text


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
    assert "2 files" in resp.text
    assert "Folder import" in resp.text
    assert "Check imported text files" in resp.text
    assert "Start coding" in resp.text
    assert ">Back</button>" in resp.text
    assert "Import more data" in resp.text
    assert "ace-folder-import-browser" in resp.text
    assert "Random sample" in resp.text
    assert "Previewing" in resp.text


def test_import_folder_accepts_file_uri(client_with_project):
    """Desktop dialogs may return a file:// URI instead of a POSIX path."""
    client, tmp_path = client_with_project

    folder = tmp_path / "texts with spaces"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    resp = client.post(
        "/api/import/folder",
        data={"path": folder.as_uri()},
    )

    assert resp.status_code == 200
    assert "1 file" in resp.text
    assert "Check imported text files" in resp.text
