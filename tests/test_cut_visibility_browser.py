"""A cut code remains available while its folder is collapsed."""

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
def test_cut_item_survives_collapsed_folder_refresh(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "cut.ace"
    conn = create_project(str(project), "Cut state")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "A sentence.", "row")
    folder_id = add_folder(conn, "Group")
    cut_id = add_code(conn, "Alpha", "#336699", parent_id=folder_id)
    beta_id = add_code(conn, "Beta", "#336699")
    add_code(conn, "Gamma", "#336699")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()

                def serve_from_test_client(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = url.path + (f"?{url.query}" if url.query else "")
                    headers = {
                        key: value for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    }
                    response = client.request(
                        request.method, path,
                        content=request.post_data_buffer,
                        headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers),
                        body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code")
                cut_row = page.locator(f'.ace-ht-row[data-code-id="{cut_id}"]')
                cut_row.click()
                page.keyboard.press("Meta+x")
                assert cut_row.evaluate(
                    "row => row.classList.contains('ace-code-row--ghost')"
                )
                folder_toggle = page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                )
                folder_toggle.click()
                assert cut_row.count() == 0

                page.evaluate("""() => {
                    window.__codebookSettleCount = 0;
                    document.addEventListener('htmx:afterSettle', () => {
                        window.__codebookSettleCount += 1;
                    });
                }""")
                with page.expect_response("**/api/codes/reorder"):
                    page.evaluate("""() => htmx.ajax('POST', '/api/codes/reorder', {
                        target: '#code-sidebar', swap: 'outerHTML',
                        values: {code_ids: '[]', current_index: 0}
                    })""")
                page.wait_for_function("window.__codebookSettleCount > 0")
                controller = "window.AceHeadlessTreePreview.getController()"
                assert page.evaluate(f"{controller}.getCutItemId()") == cut_id
                assert "Cut cleared" not in page.locator("#ace-statusbar-event").inner_text()

                def refresh_sidebar(name):
                    old_mount = page.locator("#ace-headless-tree-mount").element_handle()
                    with page.expect_response("**/api/codes/tree"):
                        page.evaluate("""name => htmx.ajax('POST', '/api/codes/folder', {
                            target: '#text-panel', swap: 'outerHTML',
                            values: {name, current_index: 0}
                        })""", name)
                    page.wait_for_function(
                        "old => document.getElementById('ace-headless-tree-mount') !== old",
                        arg=old_mount,
                    )

                refresh_sidebar("Fresh one")
                assert page.evaluate(f"{controller}.getCutItemId()") == cut_id
                assert "Cut cleared" not in page.locator("#ace-statusbar-event").inner_text()
                folder_row = page.locator(f'.ace-ht-row[data-folder-id="{folder_id}"]')
                assert folder_row.get_attribute("aria-expanded") == "false"
                assert cut_row.count() == 0
                assert page.locator('.ace-ht-row--folder').filter(
                    has_text="Fresh one"
                ).get_attribute("aria-expanded") == "true"
                folder_toggle.click()
                assert cut_row.evaluate(
                    "row => row.classList.contains('ace-code-row--ghost')"
                )
                folder_toggle.click()
                assert cut_row.count() == 0

                with sqlite3.connect(project) as stored:
                    stored.execute(
                        "UPDATE codebook_code SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (cut_id,),
                    )
                page.locator(f'.ace-ht-row[data-code-id="{beta_id}"]').click()
                with page.expect_response("**/api/codes/tree"):
                    page.keyboard.press("Alt+Shift+ArrowDown")
                page.wait_for_function(
                    f"() => {controller}.getCutItemId() === null"
                )
                assert "Cut cleared (item removed)" in page.locator(
                    "#ace-statusbar-event"
                ).inner_text()
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("view", ["coding", "audit"])
def test_move_into_collapsed_folder_focuses_visible_parent(tmp_path, engine, view):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "move-into-collapsed.ace"
    conn = create_project(project, "Collapsed folder focus")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "A sentence.", "row")
    folder_id = add_folder(conn, "Group")
    moved_id = add_code(conn, "Alpha", "#336699")
    next_id = add_code(conn, "Beta", "#663399")
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
                path = "/code" if view == "coding" else f"/code/{next_id}/view"
                page.goto(f"http://127.0.0.1:8080{path}")
                folder = page.locator(f'.ace-ht-row[data-folder-id="{folder_id}"]')
                folder.locator(".ace-ht-toggle").click()
                assert folder.get_attribute("aria-expanded") == "false"

                moved = page.locator(f'.ace-ht-row[data-code-id="{moved_id}"]')
                moved.click()
                with page.expect_response(f"**/api/codes/{moved_id}/parent") as save:
                    page.keyboard.press("Alt+ArrowRight")
                assert save.value.ok
                page.wait_for_function(
                    "id => !document.querySelector(`.ace-ht-row[data-code-id='${id}']`)",
                    arg=moved_id,
                )
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (moved_id,)
                    ).fetchone()[0] == folder_id
                assert folder.get_attribute("aria-expanded") == "false"
                assert folder.get_attribute("tabindex") == "0"
                assert page.evaluate("document.activeElement?.dataset.itemId") == folder_id
                page.keyboard.press("ArrowDown")
                page.wait_for_function(
                    "id => document.activeElement?.dataset.itemId === id", arg=next_id,
                )
            finally:
                browser.close()
