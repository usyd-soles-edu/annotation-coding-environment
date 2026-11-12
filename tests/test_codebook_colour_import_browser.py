"""Optional CSV colour mapping works in the codebook import dialog."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_import_dialog_maps_colour_column(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "codebook-colour.ace"
    conn = create_project(str(project), "Codebook colour")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One source.", "row")
    conn.close()
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("Code Label,Tint\nAccess,#123abc\n", encoding="utf-8")

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        dialog_html = client.post(
            "/api/codes/import/preview-path",
            data={"path": str(csv_path), "current_index": 0},
        ).text
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})

                def serve_from_test_client(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = url.path + (f"?{url.query}" if url.query else "")
                    headers = {
                        key: value for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    }
                    response = client.request(
                        request.method, path, content=request.post_data_buffer, headers=headers
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code")
                page.locator("#codebook-menu-btn").click()
                assert page.get_by_text("Names only or mapped columns.").is_visible()
                page.evaluate("""html => {
                    const host = document.getElementById('modal-container');
                    host.innerHTML = html;
                    const dialog = host.querySelector('dialog');
                    dialog.showModal();
                    window._aceInitCodebookImportDialog(dialog);
                }""", dialog_html)
                colour = page.locator("#codebook-map-colour")
                assert page.get_by_text("Folder/group organises codes into folders.").is_visible()
                assert page.get_by_text("Definition appears in the code hover popup.").is_visible()
                assert colour.is_visible()
                assert colour.input_value() == ""
                with page.expect_response("**/api/codes/import/preview-map"):
                    colour.select_option("Tint")
                page.wait_for_function("""() => {
                    const button = document.getElementById('codebook-import-commit');
                    return JSON.parse(button.dataset.codes)[0]?.colour === '#123abc';
                }""")
                assert "#123abc" in page.locator("#codebook-import-preview").inner_text()
                with page.expect_response("**/api/codes/import"):
                    page.locator("#codebook-import-commit").click()
                with sqlite3.connect(project) as stored:
                    row = stored.execute(
                        "SELECT colour FROM codebook_code WHERE name = 'Access' AND kind = 'code'"
                    ).fetchone()
                    assert row[0] == "#123abc"
            finally:
                browser.close()
