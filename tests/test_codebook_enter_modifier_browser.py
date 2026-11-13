"""Modified Enter on a codebook row must not apply a code."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_modified_enter_keeps_code_unapplied(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "enter.ace"
    conn = create_project(str(project), "Enter modifiers")
    add_source(conn, "S1", "One sentence.", "row")
    coder_id = list_coders(conn)[0]["id"]
    code_id = add_code(conn, "Alpha", "#336699")
    folder_id = add_folder(conn, "Group")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
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

                page.route("http://127.0.0.1:8080/**", serve)
                page.goto("http://127.0.0.1:8080/code")
                folder = page.locator(f'.ace-ht-row[data-folder-id="{folder_id}"]')
                folder.click()
                assert folder.get_attribute("aria-expanded") == "true"
                page.keyboard.press("Enter")
                assert folder.get_attribute("aria-expanded") == "false"
                page.keyboard.press("Enter")
                assert folder.get_attribute("aria-expanded") == "true"

                page.locator(".ace-sentence").first.click()
                row = page.locator(f'.ace-ht-row[data-code-id="{code_id}"]')
                row.click()
                assert page.evaluate("window.__aceFocusIndex >= 0")

                for key in ("Control+Enter", "Meta+Enter"):
                    page.keyboard.press(key)
                    page.wait_for_load_state("networkidle")
                    with sqlite3.connect(project) as stored:
                        assert stored.execute("SELECT COUNT(*) FROM annotation").fetchone()[0] == 0
                    assert row.evaluate("el => document.activeElement === el")

                with page.expect_response("**/api/code/apply-sentence"):
                    page.keyboard.press("Enter")
                with sqlite3.connect(project) as stored:
                    assert stored.execute("SELECT COUNT(*) FROM annotation").fetchone()[0] == 1
            finally:
                browser.close()
