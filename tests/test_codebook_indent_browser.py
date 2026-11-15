"""Codebook indent and outdent shortcuts keep nested parent relationships."""

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
def test_outdent_moves_code_and_folder_one_level(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "nested-outdent.ace"
    conn = create_project(str(project), "Nested outdent")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "A sentence.", "row")
    outer_id = add_folder(conn, "Outer")
    inner_id = add_folder(conn, "Inner", parent_id=outer_id)
    code_id = add_code(conn, "Alpha", "#336699", parent_id=inner_id)
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

                def assert_parent(item_id, expected_parent):
                    with sqlite3.connect(project) as saved:
                        assert saved.execute(
                            "SELECT parent_id FROM codebook_code WHERE id = ?",
                            (item_id,),
                        ).fetchone()[0] == expected_parent

                code = page.locator(f'.ace-ht-row[data-item-id="{code_id}"]')
                code.click()
                with page.expect_response(f"**/api/codes/{code_id}/parent") as moved_code:
                    page.keyboard.press("Alt+ArrowLeft")
                assert moved_code.value.ok
                page.wait_for_function(
                    "({id, parent}) => window.__aceHeadlessTreePreview.items[parent]?.children.includes(id)",
                    arg={"id": code_id, "parent": outer_id},
                )
                assert_parent(code_id, outer_id)

                inner = page.locator(f'.ace-ht-row[data-item-id="{inner_id}"]')
                inner.click()
                with page.expect_response(f"**/api/codes/{inner_id}/parent") as moved_folder:
                    page.keyboard.press("Alt+ArrowLeft")
                assert moved_folder.value.ok
                page.wait_for_function(
                    "id => window.__aceHeadlessTreePreview.items.root?.children.includes(id)",
                    arg=inner_id,
                )
                assert_parent(inner_id, None)

                inner = page.locator(f'.ace-ht-row[data-item-id="{inner_id}"]')
                inner.click()
                with page.expect_response(f"**/api/codes/{inner_id}/parent") as nested_again:
                    page.keyboard.press("Alt+ArrowRight")
                assert nested_again.value.ok
                page.wait_for_function(
                    "({id, parent}) => window.__aceHeadlessTreePreview.items[parent]?.children.includes(id)",
                    arg={"id": inner_id, "parent": outer_id},
                )
                assert_parent(inner_id, outer_id)

                page.evaluate(
                    "document.getElementById('ace-headless-tree-mount')"
                    ".dataset.codebookMode = 'readonly'"
                )
                inner.click()
                page.keyboard.press("Alt+ArrowLeft")
                assert page.locator("#ace-statusbar-event").inner_text() == (
                    "Back to source to edit the codebook"
                )
                assert_parent(inner_id, outer_id)
            finally:
                browser.close()
