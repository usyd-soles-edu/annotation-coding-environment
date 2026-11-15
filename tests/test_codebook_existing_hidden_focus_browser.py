"""Existing-code search reveals a code inside a collapsed folder."""

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
@pytest.mark.parametrize("view", ["coding", "audit"])
def test_existing_code_search_focuses_hidden_code(tmp_path, engine, view):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "hidden-existing-code.ace"
    conn = create_project(str(project), "Hidden existing code")
    add_source(conn, "S1", "Some source text.", "row")
    folder_id = add_folder(conn, "Group")
    hidden_id = add_code(conn, "Alpha", "#AA0000", parent_id=folder_id)
    viewed_id = add_code(conn, "Beta", "#0000AA")
    coder_id = list_coders(conn)[0]["id"]
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()
                creates = []

                def serve(route):
                    request = route.request
                    url = urlsplit(request.url)
                    if request.method == "POST" and url.path == "/api/codes":
                        creates.append(request)
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
                path = "/code" if view == "coding" else f"/code/{viewed_id}/view"
                page.goto(f"http://127.0.0.1:8080{path}")
                folder = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                folder.locator(".ace-ht-toggle").click()
                assert folder.get_attribute("aria-expanded") == "false"
                hidden = page.locator(f'.ace-ht-row[data-item-id="{hidden_id}"]')
                assert hidden.count() == 0

                search = page.locator("#code-search-input")
                search.fill("Alpha")
                search.press("Control+Enter")
                assert search.input_value() == ""
                assert creates == []
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Alpha'"
                    ).fetchone()[0] == 1

                assert folder.get_attribute("aria-expanded") == "true"
                hidden.wait_for()
                assert hidden.evaluate("row => document.activeElement === row")
                assert hidden.get_attribute("tabindex") == "0"
                assert page.locator(
                    '#ace-headless-tree-mount .ace-ht-row[tabindex="0"]'
                ).count() == 1
                assert page.evaluate(
                    "window.__aceHeadlessTreePreview?.tree?.getFocusedItem?.()?.getId()"
                ) == hidden_id
            finally:
                browser.close()
