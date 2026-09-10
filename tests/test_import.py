"""Tests for the import page and API routes."""

import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

import ace.services.importer as importer
from ace.app import create_app
from ace.db.connection import create_project, open_project
from ace.models.source import add_source, get_source_content, list_sources


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

    client.post("/api/import/file", data={"path": str(csv_path)})

    # Commit the import
    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert "2 sources" in resp.text
    assert "ace-import-result" in resp.text
    assert "Import complete" in resp.text
    assert '<div class="ace-import-result-count">2 sources</div>' in resp.text
    assert "Start coding" in resp.text


def test_import_commit_reports_blank_source_labels(client_with_project):
    """Blank source labels are reported and the full batch is rejected."""
    client, tmp_path = client_with_project
    csv_path = tmp_path / "blank-label.csv"
    csv_path.write_text("id,text\nA1,first\n,second\n", encoding="utf-8")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert "Source labels cannot be blank." in resp.text
    conn = open_project(tmp_path / "test.ace")
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()


def test_import_commit_skips_completely_blank_rows(client_with_project):
    """A wholly blank trailing row is reported as empty rather than invalid."""
    client, tmp_path = client_with_project
    csv_path = tmp_path / "blank-row.csv"
    csv_path.write_text("id,text\nA1,first\n,\n", encoding="utf-8")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert "Skipped 1 empty source." in resp.text
    conn = open_project(tmp_path / "test.ace")
    try:
        assert [source["display_id"] for source in list_sources(conn)] == ["A1"]
    finally:
        conn.close()


def test_import_commit_requires_text_column(client_with_project):
    """Submitting without a text column does not create empty sources."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n", encoding="utf-8")

    client.post("/api/import/file", data={"path": str(csv_path)})

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


def test_import_commit_reports_missing_id_column_plainly(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n", encoding="utf-8")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "missing", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert "Selected source label column was not found" in resp.text
    assert "Import failed" not in resp.text
    assert "KeyError" not in resp.text
    assert "&#x27;missing&#x27;" not in resp.text


def test_import_commit_reports_missing_text_column_plainly(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n", encoding="utf-8")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["missing"]'},
    )

    assert resp.status_code == 200
    assert "Selected text column &quot;missing&quot; was not found" in resp.text
    assert "Import failed" not in resp.text
    assert "0 sources" not in resp.text


def test_import_commit_reuses_parsed_tabular_data(client_with_project, monkeypatch):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n", encoding="utf-8")
    client.post("/api/import/file", data={"path": str(csv_path)})

    from ace.services import importer

    calls = 0
    original_read_tabular = importer.read_tabular

    def counted_read_tabular(path):
        nonlocal calls
        calls += 1
        return original_read_tabular(path)

    monkeypatch.setattr(importer, "read_tabular", counted_read_tabular)

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert calls == 1


def test_import_commit_multiple_text_columns_creates_one_source_per_row(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text(
        "id,reflection,feedback,group\n"
        "A1,Reflection one,Feedback one,ctrl\n"
        "A2,Reflection two,Feedback two,exp\n"
    )

    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["reflection", "feedback"]'},
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


def test_import_commit_reports_empty_rows_separately(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text(
        "id,reflection,feedback\n"
        "A1,,   \n"
        "A2,Reflection two,\n",
        encoding="utf-8",
    )

    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["reflection", "feedback"]'},
    )

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert "Skipped 1 empty source." in resp.text
    assert "already present" not in resp.text
    conn = open_project(tmp_path / "test.ace")
    try:
        sources = list_sources(conn)
        assert [source["display_id"] for source in sources] == ["A2"]
    finally:
        conn.close()


def test_import_commit_keeps_native_file_path(client_with_project):
    client, tmp_path = client_with_project

    csv_path = tmp_path / "native.csv"
    csv_path.write_text("id,text\nA1,hello\n")
    client.post("/api/import/file", data={"path": str(csv_path)})

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": '["text"]'},
    )

    assert resp.status_code == 200
    assert csv_path.exists()


def test_import_commit_rejects_non_json_text_columns_payload(client_with_project):
    """Comma-joined or otherwise non-JSON payloads get the friendly error."""
    client, tmp_path = client_with_project
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text\nA1,hello\n")
    client.post("/api/import/file", data={"path": str(csv_path)})

    for payload in ("text", "text,more", '["text"', '{"0": "text"}', "[1, 2]"):
        resp = client.post(
            "/api/import/commit",
            data={"id_column": "id", "text_columns": payload},
        )
        assert resp.status_code == 200
        assert "Choose at least one text column." in resp.text

    conn = open_project(tmp_path / "test.ace")
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()


def test_import_commit_xlsx_comma_nbsp_header_end_to_end(client_with_project):
    """A header with commas and a leading NBSP survives preview and commit."""
    client, tmp_path = client_with_project

    header = (
        "\u00a0If you used another qualitative-coding tool before ACE, think of one "
        "task you did in both tools. How did you go about that task in the other "
        "tool, and how do you go about it in ACE now?"
    )
    content = "In the other tool I coded by hand; now ACE drafts the first codes."
    xlsx_path = tmp_path / "workbook.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["participant", header])
    ws.append(["P01", content])
    wb.save(xlsx_path)
    wb.close()

    preview = client.post("/api/import/file", data={"path": str(xlsx_path)})
    assert preview.status_code == 200
    assert header in preview.text
    # The default selection is serialised as a JSON array, not comma-joined text.
    assert html.escape(json.dumps([header]), quote=True) in preview.text

    resp = client.post(
        "/api/import/commit",
        data={"id_column": "participant", "text_columns": json.dumps([header])},
    )
    assert resp.status_code == 200
    assert "1 source" in resp.text

    conn = open_project(tmp_path / "test.ace")
    try:
        sources = list_sources(conn)
        assert [source["display_id"] for source in sources] == ["P01"]
        stored = get_source_content(conn, sources[0]["id"])["content_text"]
        assert stored == content
    finally:
        conn.close()


def test_import_preview_returns_reviewed_workspace(client_with_project):
    """The legacy preview route now returns the reviewed Workspace, not a sample."""
    client, tmp_path = client_with_project

    folder = tmp_path / "prev"
    folder.mkdir()
    (folder / "doc.txt").write_text(
        "Preview content here.\nSecond line.", encoding="utf-8"
    )

    resp = client.get("/api/import/preview", params={"folder": str(folder)})

    assert resp.status_code == 200
    assert "ace-folder-preview-workspace" in resp.text
    assert "ace-folder-preview-toolbar" in resp.text
    assert "ace-folder-preview-source-header" in resp.text
    assert "data-folder-preview-row" in resp.text
    assert 'aria-current="true"' in resp.text
    assert "Preview content here.\nSecond line." in resp.text
    assert "Confirm to add 1 file to your project; 0 will be left out." in resp.text
    assert "Random sample" not in resp.text
    assert "Showing " not in resp.text
    assert '<details class="ace-folder-preview-exclusions">' in resp.text


def test_import_page_has_consistent_buttons(client_with_project):
    """Both import options use ace-wizard-option buttons, no dropzone."""
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "ace-wizard-dropzone" not in resp.text
    assert "ace-wizard-option" in resp.text
    assert 'postFragment("/api/import/folder", { path: path }, "#step-columns")' in resp.text
    assert "data-folder-preview-row" in resp.text
    assert "data-folder-preview-confirm" in resp.text
    assert 'data-repreview-required="true"' in resp.text
    assert 'showStep("step-columns")' in resp.text


class _MarkupElements(HTMLParser):
    """Collect element tags and attributes for rendered-fragment contracts."""

    def __init__(self):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _elements_with_attribute(markup: str, attribute: str) -> list[tuple[str, dict[str, str | None]]]:
    parser = _MarkupElements()
    parser.feed(markup)
    return [element for element in parser.elements if attribute in element[1]]


def test_folder_preview_canvas_display_selectors_target_only_canvas_elements(
    client_with_project,
):
    """Selection display selectors cannot resolve to per-row button metadata."""
    client, tmp_path = client_with_project
    folder = tmp_path / "display-contract"
    folder.mkdir()
    (folder / "one.txt").write_text("Short preview", encoding="utf-8")
    (folder / "two.txt").write_text("x" * 8_001, encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    assert preview.status_code == 200

    display_selectors = {
        "data-folder-preview-canvas-title": "h2",
        "data-folder-preview-canvas-meta": "span",
        "data-folder-preview-canvas-text": "pre",
        "data-folder-preview-canvas-truncated": "p",
    }
    for selector, intended_tag in display_selectors.items():
        matches = _elements_with_attribute(preview.text, selector)
        assert [tag for tag, _ in matches] == [intended_tag]

    row_elements = _elements_with_attribute(preview.text, "data-folder-preview-row")
    assert len(row_elements) == 2
    assert all(
        not set(attributes).intersection(display_selectors)
        for _, attributes in row_elements
    )

    page = client.get("/import")
    for selector in display_selectors:
        assert f'workspace.querySelector("[{selector}]")' in page.text


def test_show_step_focuses_and_announces_folder_preview_heading(client_with_project):
    """Entering the preview step focuses its heading for the live announcement."""
    client, _ = client_with_project

    page = client.get("/import")

    assert (
        'step.querySelector(".ace-wizard-title, .ace-wizard-count, '
        '.ace-folder-preview-title")'
    ) in page.text
    assert "title.focus();" in page.text
    assert "setImportMessage(title.textContent.trim(), \"\");" in page.text


# -------------------------------------------------------------------------
# Two-phase folder import: preview (no writes) then token-backed confirm.
# -------------------------------------------------------------------------


def _extract_manifest_token(fragment: str) -> str:
    match = re.search(r'name="manifest_token" value="([^"]+)"', fragment)
    assert match, "preview fragment must carry an opaque manifest token"
    return match.group(1)


def _source_display_ids(project_path: Path) -> list[str]:
    conn = open_project(project_path)
    try:
        return [source["display_id"] for source in list_sources(conn)]
    finally:
        conn.close()


def _source_ids_by_label(project_path: Path) -> dict[str, str]:
    conn = open_project(project_path)
    try:
        return {source["display_id"]: source["id"] for source in list_sources(conn)}
    finally:
        conn.close()


def _last_import_source_ids(app) -> list[str] | None:
    """The stored last-import ids; None when never set (route-layer contract)."""
    return getattr(app.state, "last_import_source_ids", None)


def _make_mixed_folder(tmp_path: Path) -> Path:
    """Nested TXT/MD plus unsupported, hidden, hidden-dir, and FIFO entries."""
    folder = tmp_path / "texts"
    (folder / "nested").mkdir(parents=True)
    (folder / "top.txt").write_text("Top document", encoding="utf-8")
    (folder / "nested" / "kept.md").write_text("Nested markdown", encoding="utf-8")
    (folder / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (folder / ".hidden.txt").write_text("hidden", encoding="utf-8")
    (folder / ".hidden-dir").mkdir()
    (folder / ".hidden-dir" / "inside.md").write_text("hidden doc", encoding="utf-8")
    if hasattr(os, "mkfifo"):
        os.mkfifo(folder / "pipe")
    return folder


def test_import_folder_preview_creates_no_sources_and_reports_totals(
    client_with_project,
):
    """Preview counts only examined regular files and never writes sources."""
    client, tmp_path = client_with_project
    folder = _make_mixed_folder(tmp_path)

    resp = client.post("/api/import/folder", data={"path": str(folder)})

    assert resp.status_code == 200
    # Three examined regular files: two reviewed ready files plus one excluded
    # unsupported file. Hidden paths and the FIFO are absent entirely.
    assert "ace-folder-preview-toolbar" in resp.text
    assert "ace-folder-preview-source-header" in resp.text
    assert resp.text.count("data-folder-preview-row") == 2
    assert 'class="ace-folder-preview-row is-selected"' in resp.text
    assert "Confirm to add 2 files to your project; 1 will be left out." in resp.text
    assert "Random sample" not in resp.text
    assert "Showing " not in resp.text
    assert "top.txt" in resp.text
    assert "nested/kept.md" in resp.text
    assert "image.png" in resp.text
    assert "Files not included (1)" in resp.text
    assert '<details class="ace-folder-preview-exclusions">' in resp.text
    assert "Not a text or Markdown file" in resp.text
    confirm_form = re.search(
        r'<form[^>]+data-folder-preview-confirm[^>]*>(.*?)</form>',
        resp.text,
        flags=re.DOTALL,
    )
    assert confirm_form
    assert re.findall(r'name="([^"]+)"', confirm_form.group(1)) == ["manifest_token"]
    assert _source_display_ids(tmp_path / "test.ace") == []


def test_import_folder_preview_opens_exclusions_when_nothing_is_importable(
    client_with_project,
):
    client, tmp_path = client_with_project
    folder = tmp_path / "unsupported"
    folder.mkdir()
    (folder / "image.png").write_bytes(b"not a text file")

    resp = client.post("/api/import/folder", data={"path": str(folder)})

    assert resp.status_code == 200
    assert "No files can be added to your project; 1 will be left out." in resp.text
    assert "Files not included (1)" in resp.text
    assert '<details class="ace-folder-preview-exclusions" open>' in resp.text
    assert "manifest_token" not in resp.text
    assert "Confirm import" not in resp.text


def test_import_folder_preview_then_confirm_creates_sources(client_with_project):
    """The ordinary journey: preview writes nothing, confirm imports the batch."""
    client, tmp_path = client_with_project
    app = client.app
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    (folder / "two.txt").write_text("Second document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    assert preview.status_code == 200
    assert _source_display_ids(tmp_path / "test.ace") == []
    assert _last_import_source_ids(app) is None

    token = _extract_manifest_token(preview.text)
    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert "2 sources" in resp.text
    assert "Import complete" in resp.text
    assert "Start coding" in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == ["one", "two"]


def test_import_folder_preview_accepts_file_uri_then_confirm(client_with_project):
    """Desktop dialogs may return a file:// URI; preview and confirm still work."""
    client, tmp_path = client_with_project
    folder = tmp_path / "texts with spaces"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": folder.as_uri()})
    assert preview.status_code == 200
    assert _source_display_ids(tmp_path / "test.ace") == []

    token = _extract_manifest_token(preview.text)
    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == ["one"]


def test_import_folder_preview_token_is_opaque(client_with_project):
    """The token carries no folder path and is an unguessable per-preview id."""
    client, tmp_path = client_with_project
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    resp = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(resp.text)

    assert str(folder) not in resp.text
    assert str(folder) not in token
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", token)
    again = client.post("/api/import/folder", data={"path": str(folder)})
    assert _extract_manifest_token(again.text) != token


def test_folder_preview_css_wraps_long_metadata_and_stacks_header():
    css = Path("src/ace/static/css/ace.css").read_text(encoding="utf-8")
    toolbar = re.search(r"\.ace-folder-preview-toolbar \{([^}]*)\}", css)
    assert toolbar and "flex-wrap: wrap" in toolbar.group(1)
    crumb = re.search(r"\.ace-folder-preview-crumb \{([^}]*)\}", css)
    assert crumb and "overflow-wrap: anywhere" in crumb.group(1)
    header = re.search(r"\.ace-folder-preview-source-header \{([^}]*)\}", css)
    assert header and "flex-wrap: wrap" in css[header.start():]
    assert ".ace-folder-preview-source-header > div { min-width: 0; }" in css
    assert "grid-template-columns: 1fr" in css


def test_folder_preview_metadata_can_shrink_and_wrap():
    css = Path("src/ace/static/css/ace.css").read_text(encoding="utf-8")

    selectors = (
        ".ace-folder-preview-crumb b",
        ".ace-folder-preview-row b,\n.ace-folder-preview-row small,\n"
        ".ace-folder-preview-exclusion b,\n.ace-folder-preview-exclusion small",
        ".ace-folder-preview-source-header > span",
    )
    for selector in selectors:
        match = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
        assert match, f"missing metadata rule for {selector}"
        declarations = match.group(1)
        assert "min-width: 0" in declarations
        assert "overflow-wrap: anywhere" in declarations

    source_meta = re.search(
        r"\.ace-folder-preview-source-header > span \{([^}]*)\}", css
    )
    assert source_meta and "flex: 1 1 auto" in source_meta.group(1)


def test_import_folder_confirm_excludes_files_added_after_preview(client_with_project):
    """Confirmation imports the saved manifest, never a fresh folder scan."""
    client, tmp_path = client_with_project
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    (folder / "late.txt").write_text("Added after preview", encoding="utf-8")

    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert "Import complete" in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == ["one"]


@pytest.mark.parametrize(
    ("mutation", "expected_detail"),
    [
        ("changed", "file changed since preview"),
        ("deleted", "file is missing"),
        ("unreadable", "file could not be read (PermissionError)"),
    ],
)
def test_import_folder_confirm_requires_repreview_and_writes_nothing(
    client_with_project, monkeypatch, mutation, expected_detail
):
    """Changed, deleted, and unreadable ready files refuse with zero writes."""
    client, tmp_path = client_with_project
    app = client.app
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    (folder / "two.txt").write_text("Second document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    if mutation == "changed":
        (folder / "one.txt").write_text("Rewritten after preview", encoding="utf-8")
    elif mutation == "deleted":
        (folder / "one.txt").unlink()
    else:

        def failing_read(path, saved_fingerprint):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(importer, "_read_validated_ready_bytes", failing_read)

    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert 'data-repreview-required="true"' in resp.text
    assert "one.txt" in resp.text
    assert expected_detail in resp.text
    assert "Preview the folder again" in resp.text
    assert "Choose folder again" in resp.text
    assert "Import complete" not in resp.text
    assert "Added " not in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == []
    assert _last_import_source_ids(app) is None


def test_import_folder_confirm_unknown_or_blank_token_requires_new_preview(
    client_with_project,
):
    client, tmp_path = client_with_project
    for token_value in ("bogus-token", ""):
        resp = client.post(
            "/api/import/folder/confirm", data={"manifest_token": token_value}
        )
        assert resp.status_code == 200
        assert 'data-repreview-required="true"' in resp.text
        assert "Import complete" not in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == []


def test_import_folder_confirm_expired_token_requires_new_preview(client_with_project):
    client, tmp_path = client_with_project
    # A zero TTL makes every manifest expire the moment it is saved.
    client.app.state.folder_import_manifests.ttl_seconds = 0.0

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert 'data-repreview-required="true"' in resp.text
    assert "Import complete" not in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == []


def test_import_folder_confirm_consumed_token_requires_new_preview(client_with_project):
    client, tmp_path = client_with_project
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    first = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert "Import complete" in first.text

    second = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert 'data-repreview-required="true"' in second.text
    assert "Import complete" not in second.text
    # The first confirmation imported exactly once; the replay imports nothing.
    assert _source_display_ids(tmp_path / "test.ace") == ["one"]


def test_import_folder_confirm_insert_failure_keeps_last_import_untouched(
    client_with_project,
):
    """A failing batch rolls back fully and never publishes last-import ids."""
    client, tmp_path = client_with_project
    app = client.app

    conn = open_project(tmp_path / "test.ace")
    try:
        conn.execute(
            "CREATE TRIGGER abort_second_source BEFORE INSERT ON source "
            "WHEN NEW.display_id = 'two' "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        conn.commit()
    finally:
        conn.close()

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    (folder / "two.txt").write_text("Second document", encoding="utf-8")
    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    app.state.last_import_source_ids = ["sentinel-id"]
    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert 'data-repreview-required="true"' in resp.text
    assert "Import complete" not in resp.text
    assert _source_display_ids(tmp_path / "test.ace") == []
    assert app.state.last_import_source_ids == ["sentinel-id"]


def test_import_folder_confirm_sets_last_import_and_retains_duplicate_accounting(
    client_with_project,
):
    """Success stores exactly the created ids; reviewed duplicates stay counted."""
    client, tmp_path = client_with_project
    app = client.app
    project_path = tmp_path / "test.ace"

    conn = open_project(project_path)
    try:
        add_source(
            conn, display_id="dup", content_text="Existing text", source_type="file"
        )
    finally:
        conn.close()

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "dup.txt").write_text("Duplicate label", encoding="utf-8")
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert "Skipped 1 source already present in this project." in resp.text
    assert _source_display_ids(project_path) == ["dup", "one"]
    assert app.state.last_import_source_ids == [
        _source_ids_by_label(project_path)["one"]
    ]


def test_import_folder_confirm_retains_empty_file_accounting(client_with_project):
    """Empty files stay skipped in the confirmed result and last-import ids."""
    client, tmp_path = client_with_project
    app = client.app
    project_path = tmp_path / "test.ace"
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "empty.txt").write_text("", encoding="utf-8")
    (folder / "filled.txt").write_text("Some text", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    resp = client.post("/api/import/folder/confirm", data={"manifest_token": token})

    assert resp.status_code == 200
    assert "1 source" in resp.text
    assert "Skipped 1 empty source." in resp.text
    assert "already present" not in resp.text
    assert _source_display_ids(project_path) == ["filled"]
    assert app.state.last_import_source_ids == [
        _source_ids_by_label(project_path)["filled"]
    ]


def test_project_create_clears_saved_folder_import_manifests(client_with_project):
    """Changing projects drops saved manifests and the last-import record."""
    client, tmp_path = client_with_project
    app = client.app
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    app.state.last_import_source_ids = ["sentinel-id"]
    other = tmp_path / "other.ace"
    created = client.post(
        "/api/project/create",
        data={"name": "Other", "path": str(other)},
    )
    assert created.status_code == 200
    assert app.state.last_import_source_ids is None

    confirm = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert 'data-repreview-required="true"' in confirm.text
    assert "Import complete" not in confirm.text

    conn = open_project(other)
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()


def _make_other_project(tmp_path: Path, with_source: bool = False) -> Path:
    """A second .ace project to switch to, optionally seeded with a source."""
    other = tmp_path / "other.ace"
    conn = create_project(str(other), "Other")
    try:
        if with_source:
            add_source(
                conn, display_id="seed", content_text="Seed text", source_type="file"
            )
    finally:
        conn.close()
    return other


def test_project_open_clears_saved_folder_import_manifests(client_with_project):
    """Switching via /api/project/open refuses tokens previewed in the old project."""
    client, tmp_path = client_with_project
    app = client.app
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    other = _make_other_project(tmp_path)
    opened = client.post("/api/project/open", data={"path": str(other)})

    assert opened.status_code == 200
    assert opened.headers["hx-redirect"] == "/import"
    assert app.state.project_path == str(other)

    confirm = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert 'data-repreview-required="true"' in confirm.text
    assert "Import complete" not in confirm.text

    conn = open_project(other)
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()

    # The switch must not break the flow: a fresh preview confirms normally.
    fresh = client.post("/api/import/folder", data={"path": str(folder)})
    fresh_token = _extract_manifest_token(fresh.text)
    ok = client.post("/api/import/folder/confirm", data={"manifest_token": fresh_token})
    assert "Import complete" in ok.text
    assert _source_display_ids(other) == ["one"]


def test_coding_page_open_clears_saved_folder_import_manifests(client_with_project):
    """Switching via /code?open= refuses tokens previewed in the old project."""
    client, tmp_path = client_with_project
    app = client.app
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    other = _make_other_project(tmp_path, with_source=True)
    opened = client.get("/code", params={"open": str(other)})

    assert opened.status_code == 200
    assert app.state.project_path == str(other)

    confirm = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert 'data-repreview-required="true"' in confirm.text
    assert "Import complete" not in confirm.text

    conn = open_project(other)
    try:
        assert [source["display_id"] for source in list_sources(conn)] == ["seed"]
    finally:
        conn.close()


def test_failed_project_open_keeps_saved_folder_import_manifests(client_with_project):
    """Only a successful switch drops manifests — a failed open stays in A."""
    client, tmp_path = client_with_project
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    preview = client.post("/api/import/folder", data={"path": str(folder)})
    token = _extract_manifest_token(preview.text)

    refused = client.post(
        "/api/project/open", data={"path": str(tmp_path / "missing.ace")}
    )
    assert refused.status_code == 200
    assert client.app.state.project_path == str(tmp_path / "test.ace")

    confirm = client.post("/api/import/folder/confirm", data={"manifest_token": token})
    assert "Import complete" in confirm.text
    assert _source_display_ids(tmp_path / "test.ace") == ["one"]


def test_import_remove_last_deletes_stored_sources(client_with_project):
    """POST /api/import/remove-last deletes the stored source ids + dependents,
    clears the stored ids, and reloads the page."""
    client, tmp_path = client_with_project
    app = client.app

    # Insert two sources directly and store their ids as the "last import".
    from ace.db.connection import open_project
    conn = open_project(tmp_path / "test.ace")
    try:
        conn.execute(
            "INSERT INTO source (id, display_id, source_type, source_column, "
            "filename, metadata_json, sort_order, created_at) "
            "VALUES ('s1', 'A', 'file', NULL, 'a.txt', NULL, 1, '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO source (id, display_id, source_type, source_column, "
            "filename, metadata_json, sort_order, created_at) "
            "VALUES ('s2', 'B', 'file', NULL, 'b.txt', NULL, 2, '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO source_content (source_id, content_text, content_hash) "
            "VALUES ('s1', 'text a', 'x'), ('s2', 'text b', 'y')"
        )
        conn.commit()
    finally:
        conn.close()

    app.state.last_import_source_ids = ["s1", "s2"]

    resp = client.post("/api/import/remove-last")
    assert resp.status_code == 200
    assert "Removed the last import." in resp.text
    assert resp.headers.get("HX-Refresh") == "true"
    # Stored ids cleared — a second call reports nothing to remove.
    assert app.state.last_import_source_ids is None

    conn = open_project(tmp_path / "test.ace")
    try:
        assert conn.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM source_content").fetchone()[0] == 0
    finally:
        conn.close()

    resp = client.post("/api/import/remove-last")
    assert resp.status_code == 200
    assert "No import to remove." in resp.text


def test_import_remove_last_reports_annotations_also_removed(client_with_project):
    """When the removed import had annotations, the status notes how many went."""
    client, tmp_path = client_with_project
    app = client.app

    from ace.db.connection import open_project
    conn = open_project(tmp_path / "test.ace")
    try:
        conn.execute(
            "INSERT INTO source (id, display_id, source_type, source_column, "
            "filename, metadata_json, sort_order, created_at) "
            "VALUES ('s1', 'A', 'file', NULL, 'a.txt', NULL, 1, '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO source_content (source_id, content_text, content_hash) "
            "VALUES ('s1', 'text a', 'x')"
        )
        # A code + coder + annotation on the imported source.
        conn.execute(
            "INSERT INTO coder (id, name) VALUES ('c1', 'alice')"
        )
        conn.execute(
            "INSERT INTO codebook_code (id, name, colour, kind, parent_id, sort_order, created_at) "
            "VALUES ('code1', 'Joy', '#ff0000', 'code', NULL, 1, '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO assignment (id, source_id, coder_id, assigned_at, updated_at) "
            "VALUES ('asg1', 's1', 'c1', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO annotation (id, source_id, coder_id, code_id, start_offset, "
            "end_offset, selected_text, created_at, updated_at) "
            "VALUES ('ann1', 's1', 'c1', 'code1', 0, 4, 'text', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    app.state.last_import_source_ids = ["s1"]

    resp = client.post("/api/import/remove-last")
    assert resp.status_code == 200
    assert "1 annotation also removed." in resp.text
    assert resp.headers.get("HX-Refresh") == "true"


def test_import_remove_last_with_no_stored_ids(client_with_project):
    """With no prior import stored, the route returns the error status."""
    client, _ = client_with_project
    app = client.app
    app.state.last_import_source_ids = None

    resp = client.post("/api/import/remove-last")
    assert resp.status_code == 200
    assert "No import to remove." in resp.text
