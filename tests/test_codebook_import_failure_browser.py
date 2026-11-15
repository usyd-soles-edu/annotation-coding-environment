"""Codebook import reports a failed save after closing its preview."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("view", ["coding", "audit"])
def test_failed_codebook_import_reports_error(tmp_path, engine, view):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "import-failure.ace"
    conn = create_project(str(project), "Import failure")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "One sentence.", "row")
    audit_code_id = add_code(conn, "Alpha", "#336699")
    conn.close()
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("Code Label,Tint\nNew Code,#123abc\n", encoding="utf-8")

    app = create_app()
    base = "http://127.0.0.1:8080"
    with TestClient(app, base_url=base) as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        preview = client.post(
            "/api/codes/import/preview-path",
            data={
                "path": str(csv_path), "current_index": 0,
                "codebook_mode": view, "current_code_id": audit_code_id,
            },
        )
        assert preview.status_code == 200
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()

                def serve(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = url.path + (f"?{url.query}" if url.query else "")
                    headers = {
                        key: value for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    }
                    response = client.request(
                        request.method, path,
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route(f"{base}/**", serve)
                path = "/code" if view == "coding" else f"/code/{audit_code_id}/view"
                page.goto(f"{base}{path}")
                page.evaluate(
                    "html => {"
                    " const host = document.getElementById('modal-container');"
                    " host.innerHTML = html;"
                    " const dialog = host.querySelector('dialog');"
                    " dialog.showModal();"
                    " window._aceInitCodebookImportDialog(dialog);"
                    "}",
                    preview.text,
                )
                with page.expect_response("**/api/codes/import/preview-map"):
                    page.locator("#codebook-map-colour").select_option("Tint")
                page.wait_for_function(
                    "() => JSON.parse(document.getElementById('codebook-import-commit')"
                    ".dataset.codes)[0]?.colour === '#123abc'"
                )
                codes_json = page.locator("#codebook-import-commit").get_attribute("data-codes")
                endpoint = f"{base}/api/codes/import"
                page.route(
                    endpoint, lambda route: route.fulfill(status=503, body="save failed"),
                    times=1,
                )
                if view == "audit":
                    page.once("dialog", lambda dialog: dialog.accept())
                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and urlsplit(response.url).path == "/api/codes/import"
                ) as failed:
                    page.locator("#codebook-import-commit").click()
                assert failed.value.status == 503
                assert not page.locator(".ace-codebook-import-dialog").is_visible()
                page.wait_for_function(
                    "document.getElementById('ace-notification-receipt')?.textContent "
                    "=== 'Could not import codebook'",
                    timeout=1000,
                )
                assert page.locator("#ace-notification-receipt").is_visible()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE name = 'New Code'"
                    ).fetchone()[0] == 0

                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and urlsplit(response.url).path == "/api/codes/import"
                ) as retried:
                    page.evaluate(
                        "([codes, mode, code]) => window.AceHeadlessTreePreview"
                        ".getController().importCodes(codes, 0, mode, code)",
                        [codes_json, view, audit_code_id],
                    )
                assert retried.value.ok
                page.wait_for_function(
                    "() => document.getElementById('ace-notification-receipt')"
                    "?.textContent.includes('Imported 1 code')"
                )
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT colour FROM codebook_code WHERE name = 'New Code'"
                    ).fetchone()[0] == "#123abc"
            finally:
                browser.close()
