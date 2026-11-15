"""F2 and Delete cannot edit the codebook during source navigation."""

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
def test_editing_denied_during_source_navigation(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "editing-denied.ace"
    conn = create_project(str(project), "Editing guard")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
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
                row = page.locator(f'.ace-ht-row[data-code-id="{code_id}"]')
                row.click()
                page.evaluate("document.body.dataset.aceNavigating = '1'")

                page.keyboard.press("F2")
                assert page.locator("#ace-statusbar-event").inner_text() == (
                    "Wait for source navigation to finish"
                )
                assert row.locator(".ace-ht-rename").count() == 0

                page.evaluate(
                    "document.querySelector('[data-headless-tree-status]').textContent = ''"
                )
                page.keyboard.press("Delete")  # tree-controller guard
                assert page.locator("[data-headless-tree-status]").inner_text() == (
                    "Wait for source navigation to finish"
                )

                # A drag may have started just before navigation. Its key
                # handler must not let F2 reach the library rename shortcut.
                page.evaluate("delete document.body.dataset.aceNavigating")
                page.keyboard.press("Control+Shift+d")
                assert page.evaluate(
                    "Boolean(window.__aceHeadlessTreePreview.tree.getState().dnd)"
                )
                page.evaluate("document.body.dataset.aceNavigating = '1'")
                page.keyboard.press("F2")
                assert row.locator(".ace-ht-rename").count() == 0

                # A double-click queues a rename for the next timer tick.
                # Navigation can start after the click but before that tick.
                page.evaluate("delete document.body.dataset.aceNavigating")
                page.keyboard.press("Escape")
                assert not page.evaluate(
                    "Boolean(window.__aceHeadlessTreePreview.tree.getState().dnd)"
                )
                page.evaluate(
                    "document.querySelector('[data-headless-tree-status]').textContent = ''"
                )
                page.evaluate("""id => {
                    const label = document.querySelector(
                        `.ace-ht-row[data-code-id='${id}'] .ace-ht-label`
                    );
                    label.dispatchEvent(new MouseEvent('dblclick', {
                        bubbles: true, detail: 2,
                    }));
                    document.body.dataset.aceNavigating = '1';
                }""", code_id)
                page.wait_for_function("""() =>
                    document.querySelector('[data-headless-tree-status]')?.textContent
                    === 'Wait for source navigation to finish'
                """)
                assert row.locator(".ace-ht-rename").count() == 0

                # A failed navigation can leave this same row mounted. A
                # later double-click must still be able to start renaming.
                page.evaluate("delete document.body.dataset.aceNavigating")
                page.evaluate("""id => document.querySelector(
                    `.ace-ht-row[data-code-id='${id}'] .ace-ht-label`
                ).dispatchEvent(new MouseEvent('dblclick', {
                    bubbles: true, detail: 2,
                }))""", code_id)
                row.locator(".ace-ht-rename").wait_for(state="visible", timeout=1000)
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT deleted_at FROM codebook_code WHERE id = ?", (code_id,)
                    ).fetchone()[0] is None
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_readonly_codebook_mode_cannot_apply_code(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "readonly-application.ace"
    conn = create_project(str(project), "Read-only codebook")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
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
                page.locator(f'.ace-ht-row[data-code-id="{code_id}"]').wait_for()
                apply_requests = page.evaluate("""id => {
                    document.getElementById('ace-headless-tree-mount').dataset.codebookMode = 'readonly';
                    window.__aceFocusIndex = 0;
                    const requests = [];
                    const originalAjax = window.htmx.ajax;
                    window.htmx.ajax = function (method, url) {
                        if (url.startsWith('/api/code/apply')) requests.push(url);
                        return originalAjax.apply(this, arguments);
                    };
                    document.dispatchEvent(new CustomEvent('ace:apply-code', {
                        detail: { codeId: id },
                    }));
                    return requests;
                }""", code_id)
                assert apply_requests == []

                with sqlite3.connect(project) as stored:
                    assert stored.execute("SELECT COUNT(*) FROM annotation").fetchone()[0] == 0
            finally:
                browser.close()
