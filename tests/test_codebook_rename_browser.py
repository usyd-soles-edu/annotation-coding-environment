"""The current tree controller handles codebook renaming across engines."""

import sqlite3
import time
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
@pytest.mark.parametrize("view", ["coding", "audit"])
@pytest.mark.parametrize("failure", ["duplicate", "server", "missing"])
def test_rejected_rename_keeps_saved_name(tmp_path, browser_name, view, failure):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "duplicate-rename.ace"
    conn = create_project(str(project), "Duplicate rename")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    first_id = add_code(conn, "Alpha", "#336699")
    add_code(conn, "Beta", "#663399")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, browser_name).launch()
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
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                path = "/code" if view == "coding" else f"/code/{first_id}/view"
                page.goto(f"http://127.0.0.1:8080{path}")
                row = page.locator(f'.ace-ht-row[data-item-id="{first_id}"]')
                row.click()
                page.keyboard.press("F2")
                rename_input = row.locator("input.ace-ht-rename")
                if failure == "server":
                    page.route(
                        f"**/api/codes/{first_id}",
                        lambda route: route.fulfill(status=500, body="save failed"),
                        times=1,
                    )
                elif failure == "missing":
                    page.route(
                        f"**/api/codes/{first_id}",
                        lambda route: route.fulfill(
                            status=404, content_type="application/json",
                            body='{"detail":"Code no longer exists"}',
                        ),
                        times=1,
                    )
                rename_input.fill("Beta" if failure == "duplicate" else "Gamma")
                with page.expect_response(f"**/api/codes/{first_id}") as save:
                    rename_input.press("Enter")
                if failure == "duplicate":
                    assert "already exists" in save.value.text()
                    page.wait_for_function(
                        "document.getElementById('ace-statusbar-event')?.textContent"
                        ".includes('An item with that name already exists.')"
                    )
                elif failure == "server":
                    assert save.value.status == 500
                    page.wait_for_function(
                        "document.getElementById('ace-notification-receipt')?.textContent "
                        "=== 'Could not rename item'",
                        timeout=1000,
                    )
                    assert page.locator("#ace-notification-receipt").is_visible()
                else:
                    assert save.value.status == 404
                    page.wait_for_function(
                        "document.getElementById('ace-notification-receipt')?.textContent "
                        "=== 'Code no longer exists'",
                        timeout=1000,
                    )
                    assert page.locator("#ace-notification-receipt").is_visible()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT name FROM codebook_code WHERE id = ?", (first_id,)
                    ).fetchone()[0] == "Alpha"
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-item-id='${id}']"
                    " .ace-ht-label`)?.textContent === 'Alpha'",
                    arg=first_id,
                )
                assert row.locator(".ace-ht-label").inner_text() == "Alpha"
                if failure in {"server", "missing"}:
                    row.click()
                    page.keyboard.press("F2")
                    row.locator("input.ace-ht-rename").fill("Gamma")
                    with page.expect_response(f"**/api/codes/{first_id}") as retry:
                        row.locator("input.ace-ht-rename").press("Enter")
                    assert retry.value.status == 200
                    page.wait_for_function(
                        "id => document.querySelector(`.ace-ht-row[data-item-id='${id}']"
                        " .ace-ht-label`)?.textContent === 'Gamma'",
                        arg=first_id,
                    )
                    receipt = page.locator("#ace-notification-receipt")
                    page.wait_for_function(
                        "() => !['Could not rename item', 'Code no longer exists'].includes("
                        "document.getElementById('ace-notification-receipt')?.textContent)",
                    )
                    assert receipt.text_content() != "Could not rename item"
                    with sqlite3.connect(project) as stored:
                        assert stored.execute(
                            "SELECT name FROM codebook_code WHERE id = ?", (first_id,)
                        ).fetchone()[0] == "Gamma"
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("input_style", ["physical", "combined_event"])
def test_failed_nested_wrap_does_not_rename_existing_parent(
    tmp_path, browser_name, input_style,
):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "failed-wrap.ace"
    conn = create_project(str(project), "Failed wrap")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    parent_id = add_folder(conn, "Group")
    add_code(conn, "Alpha", "#336699", parent_id=parent_id)
    second_id = add_code(conn, "Beta", "#663399", parent_id=parent_id)
    other_folder_id = add_folder(conn, "New folder")
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
                page.locator(f'.ace-ht-row[data-item-id="{second_id}"]').click()
                with page.expect_response(f"**/api/codes/{second_id}/indent-promote") as result:
                    if input_style == "physical":
                        page.keyboard.press("Alt+Shift+ArrowRight")
                    else:
                        page.locator(f'.ace-ht-row[data-item-id="{second_id}"]').dispatch_event(
                            "keydown", {
                                "key": "ArrowRight", "altKey": True, "shiftKey": True,
                                "bubbles": True, "cancelable": True,
                            },
                        )
                assert result.value.status == 200
                assert "already exists" in result.value.text()
                page.wait_for_timeout(200)
                assert page.locator("input.ace-ht-rename").count() == 0
                assert page.locator(
                    f'.ace-ht-row[data-item-id="{parent_id}"] .ace-ht-label'
                ).inner_text() == "Group"
                assert page.evaluate("document.activeElement?.dataset.itemId") == second_id
                with sqlite3.connect(project) as saved:
                    assert saved.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (second_id,)
                    ).fetchone()[0] == parent_id
                    assert saved.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (other_folder_id,)
                    ).fetchone()[0] is None
            finally:
                browser.close()


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
                page.evaluate("""() => {
                    window.__aceRenameTestSettleCount = 0;
                    document.addEventListener('htmx:afterSettle', () => {
                        window.__aceRenameTestSettleCount += 1;
                    });
                }""")

                def save_rename(input_locator, item_id, name):
                    input_locator.fill(name)
                    previous_tree = page.evaluate_handle("window.__aceHeadlessTreePreview.tree")
                    previous_settles = page.evaluate("window.__aceRenameTestSettleCount")
                    with page.expect_response(
                        lambda response: response.request.method == "PUT"
                        and urlsplit(response.url).path == f"/api/codes/{item_id}"
                    ) as save:
                        input_locator.press("Enter")
                    assert save.value.ok
                    page.wait_for_function(
                        "count => window.__aceRenameTestSettleCount > count",
                        arg=previous_settles,
                    )
                    page.wait_for_function(
                        "old => window.__aceHeadlessTreePreview?.tree !== old",
                        arg=previous_tree,
                    )
                    page.wait_for_function(
                        "({id, name}) => window.__aceHeadlessTreePreview?.items[id]?.name === name && document.querySelector(`.ace-ht-row[data-item-id='${id}'] .ace-ht-label`)?.textContent === name",
                        arg={"id": item_id, "name": name},
                    )
                    previous_tree.dispose()

                folder = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                folder.click()
                page.wait_for_function(
                    "id => window.__aceHeadlessTreePreview.tree.getFocusedItem()?.getId() === id",
                    arg=folder_id,
                )
                page.keyboard.press("F2")
                save_rename(folder.locator("input.ace-ht-rename"), folder_id, "Cluster")

                code = page.locator(f'.ace-ht-row[data-item-id="{code_id}"]')
                code.locator(".ace-ht-label").dblclick()
                save_rename(code.locator("input.ace-ht-rename"), code_id, "Beta")

                next_code = page.locator(f'.ace-ht-row[data-item-id="{next_code_id}"]')
                def slow_tree(route):
                    time.sleep(0.8)
                    serve_from_test_client(route)

                page.route("**/api/codes/tree", slow_tree, times=1)
                next_code.click()
                page.keyboard.press("Alt+Shift+ArrowRight")
                new_folder_name = page.locator("input.ace-ht-rename")
                new_folder_name.wait_for()
                assert new_folder_name.evaluate("input => document.activeElement === input")
                new_folder_id = new_folder_name.get_attribute("data-item-id")
                save_rename(new_folder_name, new_folder_id, "Bundle")

                next_code.click()
                page.keyboard.press("Alt+Shift+ArrowRight")
                nested_folder_name = page.locator("input.ace-ht-rename")
                nested_folder_id = nested_folder_name.get_attribute("data-item-id")
                save_rename(nested_folder_name, nested_folder_id, "Inside")
                with sqlite3.connect(project) as saved:
                    nested_id = saved.execute(
                        "SELECT id FROM codebook_code WHERE name = 'Inside' AND kind = 'folder'"
                    ).fetchone()[0]
                    assert saved.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (nested_id,)
                    ).fetchone()[0] is not None
                    assert saved.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (next_code_id,)
                    ).fetchone()[0] == nested_id

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
                page.wait_for_function(
                    "document.querySelector('.cv-code-name')?.textContent === 'Audit Beta'"
                )
                page.reload()
                audit_code.wait_for()
                assert audit_code.locator(".ace-ht-label").inner_text() == "Audit Beta"
                assert page.locator("#code-view").get_attribute("data-code-id") == code_id
            finally:
                browser.close()
