"""The audit sidebar can preview and commit a CSV codebook import."""

import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_audit_import_dialog_cancel_then_commit(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "audit-import.ace"
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("Code Label,Tint\nAccess,#123abc\n", encoding="utf-8")
    conn = create_project(str(project), "Audit import")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One source.", "row")
    current_code_id = add_code(conn, "Current", "#AA0000")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})

                def serve_from_test_client(route):
                    request = route.request
                    url = urlsplit(request.url)
                    if url.path == "/api/native/pick-file":
                        route.fulfill(json={"path": str(csv_path)})
                        return
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
                audit_url = f"http://127.0.0.1:8080/code/{current_code_id}/view"
                page.goto(audit_url)
                page.locator("#codebook-menu-btn").click()
                with page.expect_response("**/api/codes/import/preview-path") as preview:
                    page.locator("#codebook-menu-import-btn").click()
                assert preview.value.status == 200
                dialog = page.locator(".ace-codebook-import-dialog")
                dialog.wait_for(state="visible", timeout=5000)
                page.wait_for_function(
                    "document.querySelector('.ace-codebook-import-dialog')?.dataset.codebookImportReady === '1'",
                    timeout=5000,
                )
                page.locator("#codebook-import-title").press("Escape")
                dialog.wait_for(state="hidden", timeout=5000)
                assert page.url == audit_url

                page.locator("#codebook-menu-btn").click()
                page.locator("#codebook-menu-import-btn").click()
                dialog.wait_for(state="visible", timeout=5000)
                page.wait_for_function(
                    "document.querySelector('.ace-codebook-import-dialog')?.dataset.codebookImportReady === '1'",
                    timeout=5000,
                )
                page.locator("#codebook-import-title").press("v")
                assert page.url == audit_url
                assert dialog.is_visible()
                match_tab = page.locator("#codebook-import-tab-match")
                review_tab = page.locator("#codebook-import-tab-review")
                match_tab.focus()
                match_tab.press("ArrowRight")
                assert review_tab.get_attribute("aria-selected") == "true"
                review_tab.press("ArrowLeft")
                assert match_tab.get_attribute("aria-selected") == "true"
                requests = []
                page.on("request", lambda request: requests.append(request))
                match_tab.press("z")
                assert not any(request.url.endswith("/api/undo") for request in requests)
                with page.expect_response("**/api/codes/import/preview-map"):
                    page.locator("#codebook-map-colour").select_option("Tint")
                page.wait_for_function("""() => {
                    const button = document.getElementById('codebook-import-commit');
                    return JSON.parse(button.dataset.codes)[0]?.colour === '#123abc';
                }""")

                page.once("dialog", lambda confirmation: confirmation.dismiss())
                page.locator("#codebook-import-commit").click()
                assert dialog.is_visible()
                assert not any(request.url.endswith("/api/codes/import") for request in requests)
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Access'"
                    ).fetchone()[0] == 0

                page.once("dialog", lambda confirmation: confirmation.accept())
                with page.expect_response("**/api/codes/import") as imported:
                    page.locator("#codebook-import-commit").click()
                request_data = parse_qs(imported.value.request.post_data)
                assert request_data["codebook_mode"] == ["audit"]
                assert request_data["current_code_id"] == [current_code_id]
                assert page.url == audit_url
                page.locator(".ace-ht-row--code", has_text="Access").wait_for(timeout=5000)
                assert page.locator(f'.ace-ht-row[data-item-id="{current_code_id}"]').count() == 1
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT colour FROM codebook_code WHERE name = 'Access'"
                    ).fetchone()[0] == "#123abc"
            finally:
                browser.close()
