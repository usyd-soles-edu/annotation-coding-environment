"""Tests for project create/open API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def tmp_project(tmp_path):
    """Create a valid .ace project file, close the connection, return the path."""
    db_path = tmp_path / "existing.ace"
    conn = create_project(str(db_path), "Existing")
    conn.close()
    return db_path


# ── Create ──────────────────────────────────────────────────────────────


def test_landing_project_actions_are_keyboard_named(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert '<a id="new-project-link"' in resp.text
    assert 'href="/new-project"' in resp.text
    assert "<button" in resp.text and "Open project" in resp.text
    assert 'id="open-existing-btn"' in resp.text
    assert 'id="open-existing-btn" class="ace-home-action"' in resp.text
    assert 'type="button" aria-keyshortcuts="o"' in resp.text
    assert 'id="open-existing-btn"' in resp.text and "disabled" not in resp.text.split('id="open-existing-btn"', 1)[1].split(">", 1)[0]
    assert '<span class="ace-home-action-label">Open project</span>' in resp.text
    assert 'id="new-project-link" class="ace-home-action"' in resp.text
    assert 'aria-keyshortcuts="n"' in resp.text
    assert '<span class="ace-home-action-label">New project</span>' in resp.text
    assert 'id="resume-link"' in resp.text
    assert "ace-home-section--resume" in resp.text
    assert "Quick resume" in resp.text
    assert 'id="tools-title" class="ace-home-section-title">Tools</h2>' in resp.text
    assert 'aria-keyshortcuts="a"' in resp.text
    assert 'id="ace-home-shortcuts" class="ace-home-shortcuts"' in resp.text
    assert '<span class="ace-home-shortcuts-title">Shortcuts</span>' in resp.text
    assert '<span class="ace-home-shortcut-pair"><kbd>n</kbd><span>New</span></span>' in resp.text
    assert '<span class="ace-home-shortcut-pair"><kbd>o</kbd><span>Open</span></span>' in resp.text
    assert '<span class="ace-home-shortcut-pair"><kbd>a</kbd><span>Agreement</span></span>' in resp.text
    assert 'id="ace-home-message"' in resp.text
    assert 'id="new-project-form"' not in resp.text
    assert "Cloud-synced folders" not in resp.text


def test_new_project_page_is_minimal_and_keyboard_named(client):
    resp = client.get("/new-project")
    assert resp.status_code == 200
    assert '<main class="ace-task-page ace-task-page--narrow">' in resp.text
    assert 'href="/" class="ace-back" aria-keyshortcuts="Escape"' in resp.text
    assert '<h1 id="new-project-title" class="ace-task-title">New project</h1>' in resp.text
    assert 'id="new-project-form"' in resp.text
    assert 'id="new-project-input"' in resp.text
    assert 'id="choose-project-folder-btn"' in resp.text
    assert 'id="create-project-btn"' in resp.text
    assert 'id="ace-task-message"' in resp.text
    assert "Annotation Coding Environment" not in resp.text.split('<main class="ace-task-page', 1)[1]


def test_agreement_page_has_task_landmarks_and_progress_state(client):
    resp = client.get("/agreement")
    assert resp.status_code == 200
    assert '<main class="ace-agreement-page">' in resp.text
    assert 'id="ace-agreement-title" class="ace-agreement-title" tabindex="-1"' in resp.text
    assert "data-agreement-pick-start" in resp.text
    assert 'id="ace-agreement-progress-fill"' in resp.text
    assert 'role="progressbar"' in resp.text
    assert 'aria-valuemin="0"' in resp.text
    assert 'aria-valuemax="100"' in resp.text
    assert 'aria-valuenow="0"' in resp.text


def test_create_project(client, tmp_path):
    """POST /api/project/create creates .ace file and redirects."""
    path = str(tmp_path / "new.ace")
    resp = client.post("/api/project/create", data={"name": "Test", "path": path})
    assert Path(path).exists()
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_create_project_accepts_file_uri(client, tmp_path):
    """Desktop file pickers may return file:// URIs."""
    path = tmp_path / "native folder" / "new.ace"
    path.parent.mkdir()

    resp = client.post(
        "/api/project/create",
        data={"name": "Test", "path": path.as_uri()},
    )

    assert path.exists()
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_create_project_overwrite_dialog(client, tmp_project):
    """Existing file shows overwrite dialog."""
    resp = client.post(
        "/api/project/create", data={"name": "Test", "path": str(tmp_project)}
    )
    assert "overwrite" in resp.text.lower() or "already exists" in resp.text.lower()


def test_create_project_existing_returns_overwrite_dialog(client, tmp_project):
    resp = client.post(
        "/api/project/create",
        data={"name": "Existing", "path": str(tmp_project)},
    )
    assert resp.status_code == 200
    assert 'id="project-overwrite-dialog"' in resp.text
    assert "<dialog" in resp.text
    assert 'aria-modal="true"' in resp.text
    assert "A project already exists here" in resp.text
    assert "Overwrite project" in resp.text
    assert str(tmp_project.name) in resp.text
    assert 'name="overwrite"' in resp.text
    assert 'value="true"' in resp.text
    assert "project-overwrite-panel" not in resp.text


def test_create_project_overwrite_confirmed(client, tmp_project):
    """Overwrite=true deletes existing file and creates fresh project."""
    resp = client.post(
        "/api/project/create",
        data={"name": "Test", "path": str(tmp_project), "overwrite": "true"},
    )
    assert tmp_project.exists()
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


# ── Open ────────────────────────────────────────────────────────────────


def test_open_project(client, tmp_project):
    """POST /api/project/open sets state and redirects."""
    resp = client.post("/api/project/open", data={"path": str(tmp_project)})
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_open_project_accepts_file_uri(client, tmp_project):
    """Desktop file pickers may return file:// URIs for existing projects."""
    resp = client.post("/api/project/open", data={"path": tmp_project.as_uri()})
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_open_project_redirects_to_import(client, tmp_project):
    """Project with no sources redirects to /import."""
    resp = client.post("/api/project/open", data={"path": str(tmp_project)})
    redirect = resp.headers.get("HX-Redirect") or resp.headers.get("hx-redirect")
    assert redirect == "/import"


def test_open_invalid_file(client, tmp_path):
    """Non-.ace file returns error toast, not 500."""
    bad = tmp_path / "bad.ace"
    bad.write_text("not a database")
    resp = client.post("/api/project/open", data={"path": str(bad)})
    assert resp.status_code == 200  # toast error, not 500


def test_create_project_with_coder_name(client, tmp_path):
    """POST /api/project/create stores the provided coder name."""
    import sqlite3

    path = str(tmp_path / "named.ace")
    resp = client.post(
        "/api/project/create",
        data={"name": "Test", "path": path, "coder_name": "Alice"},
    )
    assert Path(path).exists()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    coder = conn.execute("SELECT name FROM coder LIMIT 1").fetchone()
    conn.close()
    assert coder["name"] == "Alice"


def test_open_missing_file(client, tmp_path):
    """Missing file returns error toast."""
    resp = client.post(
        "/api/project/open", data={"path": str(tmp_path / "gone.ace")}
    )
    assert resp.status_code == 200
    assert "not found" in resp.text.lower() or "toast" in resp.text.lower()
