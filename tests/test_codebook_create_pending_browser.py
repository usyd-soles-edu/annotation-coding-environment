"""Queued codebook creation keeps its pending state until the request completes."""

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
@pytest.mark.parametrize("kind", ["folder", "code"])
def test_queued_create_keeps_pending_status(tmp_path, engine, kind):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "queued-create.ace"
    conn = create_project(str(project), "Queued create")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            released_blocker = False
            released_creates = 0
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
                page.wait_for_function("window.AceHeadlessTreePreview?.getController?.()?.rootElement?.()")
                path = "/api/codes/folder" if kind == "folder" else "/api/codes"
                page.evaluate("""path => {
                    const open = XMLHttpRequest.prototype.open;
                    const send = XMLHttpRequest.prototype.send;
                    window.__releaseCreateRequests = [];
                    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                        const pathname = new URL(url, location.origin).pathname;
                        this.__holdBlocker = pathname === '/api/codes/folder' && !window.__blockerHeld;
                        if (this.__holdBlocker) window.__blockerHeld = true;
                        this.__holdCreate = pathname === path && !this.__holdBlocker;
                        return open.call(this, method, url, ...rest);
                    };
                    XMLHttpRequest.prototype.send = function (body) {
                        if (this.__holdBlocker) {
                            window.__releaseCodebookRequest = () => send.call(this, body);
                            return;
                        }
                        if (this.__holdCreate) {
                            window.__releaseCreateRequests.push(() => send.call(this, body));
                            return;
                        }
                        return send.call(this, body);
                    };
                    window.__createRequestsStarted = 0;
                    window.__trailingRequestsStarted = 0;
                    document.addEventListener('htmx:beforeRequest', event => {
                        if (event.detail?.requestConfig?.parameters?.name?.startsWith('Waiting item')) {
                            window.__createRequestsStarted += 1;
                        }
                        if (event.detail?.requestConfig?.path === '/api/codes/reorder') {
                            window.__trailingRequestsStarted += 1;
                        }
                    });
                    htmx.ajax('POST', '/api/codes/folder', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: { name: 'Blocking folder', current_index: 0 },
                    });
                }""", path)
                page.wait_for_function("window.__releaseCodebookRequest !== undefined")
                search = page.locator("#code-search-input")
                search.fill("Waiting item 1")
                search.press("Shift+Enter" if kind == "folder" else "Control+Enter")
                search.fill("Waiting item 2")
                search.press("Shift+Enter" if kind == "folder" else "Control+Enter")
                page.evaluate("""() => htmx.ajax('POST', '/api/codes/reorder', {
                    target: '#code-sidebar', swap: 'outerHTML',
                    values: { code_ids: '[]', current_index: 0 },
                })""")
                assert page.evaluate("window.__createRequestsStarted") == 0
                assert page.evaluate("window.__trailingRequestsStarted") == 0
                assert page.locator("[data-headless-tree-status]").text_content() == "Creating"
                page.evaluate("window.__oldMount = document.getElementById('ace-headless-tree-mount')")
                page.evaluate("window.__releaseCodebookRequest()")
                released_blocker = True
                page.wait_for_function("window.__releaseCreateRequests.length === 1")
                page.wait_for_function("""() =>
                    document.getElementById('ace-headless-tree-mount') !== window.__oldMount &&
                    document.getElementById('ace-headless-tree-mount')?.dataset.aceTreeController === 'headless'
                """, timeout=5000)
                assert page.locator("[data-headless-tree-status]").text_content() == "Creating"
                with page.expect_response(f"**{path}", timeout=5000):
                    page.evaluate("window.__releaseCreateRequests[0]()")
                    released_creates = 1
                page.locator(f'.ace-ht-row[data-kind="{kind}"]', has_text="Waiting item 1").wait_for()
                page.wait_for_function("window.__releaseCreateRequests.length === 2")
                assert page.locator("[data-headless-tree-status]").text_content() == "Creating"
                with page.expect_response("**/api/codes/reorder", timeout=5000):
                    with page.expect_response(f"**{path}", timeout=5000):
                        page.evaluate("window.__releaseCreateRequests[1]()")
                        released_creates = 2
                page.locator(f'.ace-ht-row[data-kind="{kind}"]', has_text="Waiting item 2").wait_for()
                page.wait_for_function("""() =>
                    document.querySelector('[data-headless-tree-status]')?.textContent === ''
                """)
                assert page.evaluate("window.__createRequestsStarted") == 2
                assert page.evaluate("window.__trailingRequestsStarted") == 1
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT name FROM codebook_code WHERE name LIKE 'Waiting item %' "
                        "AND kind = ? ORDER BY name", (kind,)
                    ).fetchall() == [("Waiting item 1",), ("Waiting item 2",)]
            finally:
                if not released_blocker:
                    page.evaluate("window.__releaseCodebookRequest?.()")
                page.evaluate("""released =>
                    window.__releaseCreateRequests?.slice(released).forEach(send => send())
                """, released_creates)
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("first_to_finish", ["create", "drag"])
def test_create_and_drag_keep_each_others_pending_status(tmp_path, engine, first_to_finish):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "create-and-drag.ace"
    conn = create_project(str(project), "Create and drag")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    first_id = add_code(conn, "First", "#123456")
    add_code(conn, "Second", "#654321")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            released = set()
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
                page.wait_for_function("window.AceHeadlessTreePreview?.getController?.()?.rootElement?.()")
                page.evaluate("""() => {
                    const open = XMLHttpRequest.prototype.open;
                    const send = XMLHttpRequest.prototype.send;
                    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                        const path = new URL(url, location.origin).pathname;
                        this.__holdKind = path === '/api/codes' ? 'create'
                            : path === '/api/codes/reorder-in-scope' ? 'drag' : '';
                        return open.call(this, method, url, ...rest);
                    };
                    XMLHttpRequest.prototype.send = function (body) {
                        if (this.__holdKind) {
                            window.__releaseMutation ||= {};
                            window.__releaseMutation[this.__holdKind] = () => send.call(this, body);
                            return;
                        }
                        return send.call(this, body);
                    };
                }""")

                def start_create():
                    search = page.locator("#code-search-input")
                    search.fill("New code")
                    search.press("Control+Enter")
                    page.wait_for_function("window.__releaseMutation?.create !== undefined")

                def start_drag():
                    page.locator(f'.ace-ht-row[data-code-id="{first_id}"]').focus()
                    page.keyboard.press("Control+Shift+d")
                    page.keyboard.press("ArrowDown")
                    page.keyboard.press("Enter")
                    page.wait_for_function("window.__releaseMutation?.drag !== undefined")

                if first_to_finish == "drag":
                    start_drag()
                    start_create()
                else:
                    start_create()
                    start_drag()

                assert page.locator("[data-headless-tree-status]").text_content() == "Saving"
                first = first_to_finish
                second = "drag" if first == "create" else "create"
                first_path = "/api/codes" if first == "create" else "/api/codes/reorder-in-scope"
                second_path = "/api/codes" if second == "create" else "/api/codes/reorder-in-scope"
                with page.expect_response(f"**{first_path}", timeout=5000):
                    page.evaluate("kind => window.__releaseMutation[kind]()", first)
                    released.add(first)
                page.wait_for_function("""expected =>
                    document.querySelector('[data-headless-tree-status]')?.textContent === expected
                """, arg="Creating" if first == "drag" else "Saving")
                with page.expect_response(f"**{second_path}", timeout=5000):
                    page.evaluate("kind => window.__releaseMutation[kind]()", second)
                    released.add(second)
                page.wait_for_function("""() =>
                    document.querySelector('[data-headless-tree-status]')?.textContent === ''
                """)
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE name = 'New code'"
                    ).fetchone()[0] == 1
            finally:
                for kind in {"create", "drag"} - released:
                    page.evaluate("kind => window.__releaseMutation?.[kind]?.()", kind)
                browser.close()
