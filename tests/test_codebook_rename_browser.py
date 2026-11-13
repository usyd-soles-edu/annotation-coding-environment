"""The current tree controller handles codebook renaming across engines."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_code_folder_and_new_wrapper_rename_use_tree_controller(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "rename.ace"
    conn = create_project(str(project), "Rename")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
    next_code_id = add_code(conn, "Gamma", "#663399")
    folder_id = add_folder(conn, "Group")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, browser_name).launch()
            try:
                page = browser.new_page()
                page.set_default_timeout(8000)

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
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code")

                folder = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                folder.click()
                page.wait_for_function(
                    "id => window.__aceHeadlessTreePreview.tree.getFocusedItem()?.getId() === id",
                    arg=folder_id,
                )
                page.keyboard.press("F2")
                folder.locator("input.ace-ht-rename").fill("Cluster")
                folder.locator("input.ace-ht-rename").press("Enter")
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-item-id='${id}'] .ace-ht-label`)?.textContent === 'Cluster'",
                    arg=folder_id,
                )

                code = page.locator(f'.ace-ht-row[data-item-id="{code_id}"]')
                code.locator(".ace-ht-label").dblclick()
                code.locator("input.ace-ht-rename").fill("Beta")
                code.locator("input.ace-ht-rename").press("Enter")
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-item-id='${id}'] .ace-ht-label`)?.textContent === 'Beta'",
                    arg=code_id,
                )

                next_code = page.locator(f'.ace-ht-row[data-item-id="{next_code_id}"]')
                next_code.click()
                page.keyboard.press("Alt+Shift+ArrowRight")
                new_folder_name = page.locator("input.ace-ht-rename")
                new_folder_name.fill("Bundle")
                new_folder_name.press("Enter")
                page.wait_for_function(
                    "() => [...document.querySelectorAll('.ace-ht-row--folder .ace-ht-label')].some(el => el.textContent === 'Bundle')"
                )

                page.goto(f"http://127.0.0.1:8080/code/{code_id}/view")
                audit_code = page.locator(f'.ace-ht-row[data-item-id="{code_id}"]')
                audit_code.wait_for()
                audit_code.click()
                page.wait_for_function(
                    "id => window.__aceHeadlessTreePreview.tree.getFocusedItem()?.getId() === id",
                    arg=code_id,
                )
                page.keyboard.press("F2")
                audit_code.locator("input.ace-ht-rename").fill("Audit Beta")
                with page.expect_response(
                    lambda response: response.request.method == "PUT"
                    and urlsplit(response.url).path == f"/api/codes/{code_id}"
                ) as save:
                    audit_code.locator("input.ace-ht-rename").press("Enter")
                assert save.value.ok
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-item-id='${id}'] .ace-ht-label`)?.textContent === 'Audit Beta'",
                    arg=code_id,
                )
                page.reload()
                audit_code.wait_for()
                assert audit_code.locator(".ace-ht-label").inner_text() == "Audit Beta"
                assert page.locator("#code-view").get_attribute("data-code-id") == code_id
            finally:
                browser.close()
