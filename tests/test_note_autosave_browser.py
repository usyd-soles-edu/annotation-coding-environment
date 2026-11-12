"""Source-note drafts survive failed saves and overlapping edits."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("failure", ["http", "network"])
def test_failed_note_save_blocks_navigation_then_retries(tmp_path, engine, failure):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Notes")
    coder_id = list_coders(conn)[0]["id"]
    first_id = add_source(conn, "S1", "First source.", "row")
    add_source(conn, "S2", "Second source.", "row")
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
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator("#note-pill").click()
                page.locator("#note-pill").click()

                def fail_note_save(route):
                    if failure == "http":
                        route.fulfill(status=500, body="save failed")
                    else:
                        route.abort("failed")

                page.route(f"**/api/source-note/{first_id}", fail_note_save)
                page.locator("#note-textarea").fill("Draft survives")
                navigation_requests = []
                page.on(
                    "request",
                    lambda request: navigation_requests.append(request)
                    if urlsplit(request.url).path == "/api/navigation" else None,
                )
                page.evaluate("window.aceNavigate(1)")
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent.includes('Note save failed')"
                )
                page.wait_for_function("!document.querySelector('#note-textarea').readOnly")
                assert page.evaluate("window.__aceCurrentIndex") == 0
                assert page.locator("#note-textarea").input_value() == "Draft survives"
                assert navigation_requests == []
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == 0

                page.unroute(f"**/api/source-note/{first_id}")
                page.evaluate("window.aceNavigate(1)")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                page.wait_for_function("!document.body.dataset.aceNavigating")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == "Draft survives"
                page.evaluate("window.aceNavigate(0)")
                page.wait_for_function("window.__aceCurrentIndex === 0")
                assert page.locator("#note-textarea").input_value() == "Draft survives"

                # A clean local draft must yield to a later edit from another
                # tab, both on a fresh navigation and on a same-source OOB swap.
                page.evaluate("window.aceNavigate(1)")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                page.wait_for_function("!document.body.dataset.aceNavigating")
                assert client.put(
                    f"/api/source-note/{first_id}", data={"note_text": "Other tab edit"}
                ).status_code == 200
                page.evaluate("window.aceNavigate(0)")
                page.wait_for_function("window.__aceCurrentIndex === 0")
                assert page.locator("#note-textarea").input_value() == "Other tab edit"

                assert client.put(
                    f"/api/source-note/{first_id}", data={"note_text": "Newest tab edit"}
                ).status_code == 200
                page.evaluate("""() => window.htmx.ajax('POST', '/api/navigation', {
                    target: 'body', swap: 'outerHTML',
                    values: {from_index: 0, to_index: 0, note_open: true,
                             record_undo: false, history_mode: 'none'},
                })""")
                page.wait_for_function(
                    "document.querySelector('#note-textarea')?.value === 'Newest tab edit'"
                )
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_navigation_drains_serial_note_saves(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Notes")
    coder_id = list_coders(conn)[0]["id"]
    first_id = add_source(conn, "S1", "First source.", "row")
    add_source(conn, "S2", "Second source.", "row")
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
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator("#note-pill").click()
                page.locator("#note-pill").click()
                page.evaluate("""() => {
                    const original = window.fetch.bind(window);
                    window.__noteSends = [];
                    window.fetch = (url, options) => {
                        if (!String(url).startsWith('/api/source-note/')) {
                            return original(url, options);
                        }
                        return new Promise(resolve => {
                            window.__noteSends.push({
                                text: new URLSearchParams(options.body).get('note_text'),
                                release: () => resolve(original(url, options)),
                            });
                        });
                    };
                }""")

                page.locator("#note-textarea").fill("First draft")
                page.wait_for_function("window.__noteSends.length === 1")
                page.locator("#note-textarea").fill("Latest draft")
                page.evaluate("window.aceNavigate(1)")
                assert page.evaluate("window.__noteSends.length") == 1
                assert page.evaluate("window.__aceCurrentIndex") == 0
                page.evaluate("window.__noteSends[0].release()")
                page.wait_for_function("window.__noteSends.length === 2")
                assert page.evaluate("window.__noteSends[1].text") == "Latest draft"
                assert page.evaluate("window.__aceCurrentIndex") == 0
                page.evaluate("window.__noteSends[1].release()")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                page.wait_for_function("!document.body.dataset.aceNavigating")
                assert page.evaluate("window.__noteSends.length") == 2
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == "Latest draft"
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_response_started_before_save_keeps_new_note_and_caret(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Notes")
    coder_id = list_coders(conn)[0]["id"]
    first_id = add_source(conn, "S1", "First source.", "row")
    second_id = add_source(conn, "S2", "Second source.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()

                def serve(route, *, hold=False):
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
                    payload = (route, response)
                    if hold:
                        held.append(payload)
                    else:
                        route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers), body=response.content,
                        )

                held = []
                page.route("http://127.0.0.1:8080/**", lambda route: serve(route))
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator("#note-pill").click()
                page.locator("#note-pill").click()

                # Render a response while the server note is still empty, but
                # delay delivering its HTML until after the new note is saved.
                page.route("**/api/codes/folder", lambda route: serve(route, hold=True))
                page.evaluate("""() => {
                    window.__noteSwapDone = false;
                    document.body.addEventListener('htmx:oobAfterSwap', event => {
                        if (event.detail?.target?.id === 'ace-right-inspector') {
                            window.__noteSwapDone = true;
                        }
                    }, {once: true});
                    void window.htmx.ajax('POST', '/api/codes/folder', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {name: 'Delayed folder', current_index: 0},
                    });
                }""")
                page.wait_for_timeout(100)
                assert len(held) == 1
                assert "New note" not in held[0][1].text

                page.locator("#note-textarea").fill("New note")
                page.wait_for_function(
                    "document.querySelector('#note-status')?.textContent === 'Saved'"
                )
                page.locator("#note-textarea").evaluate("el => el.setSelectionRange(3, 3)")
                assert page.locator("#note-textarea").evaluate("el => el.selectionStart") == 3
                route, response = held.pop()
                route.fulfill(
                    status=response.status_code,
                    headers=dict(response.headers), body=response.content,
                )
                page.wait_for_function("window.__noteSwapDone")
                assert page.locator("#note-textarea").input_value() == "New note"
                assert page.locator("#note-textarea").evaluate("el => el.selectionStart") == 3
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == "New note"

                # Undo/redo can switch sources outside aceNavigate's save
                # gate. An old source's late acknowledgement must not mark
                # the destination source as having a note or a saved draft.
                page.evaluate("""() => {
                    const original = window.fetch.bind(window);
                    window.__lateNoteSave = null;
                    window.fetch = (url, options) => {
                        if (!String(url).startsWith('/api/source-note/')) {
                            return original(url, options);
                        }
                        return new Promise(resolve => {
                            window.__lateNoteSave = () => resolve(original(url, options));
                        });
                    };
                }""")
                page.locator("#note-textarea").fill("Late old-source save")
                page.wait_for_function("typeof window.__lateNoteSave === 'function'")
                page.evaluate("""() => window.htmx.ajax('POST', '/api/navigation', {
                    target: 'body', swap: 'outerHTML',
                    values: {from_index: 0, to_index: 1, note_open: true,
                             record_undo: false, history_mode: 'none'},
                })""")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                page.wait_for_function(
                    "id => document.querySelector('#note-textarea')?.getAttribute('data-source-id') === id",
                    arg=second_id,
                )
                page.wait_for_function(
                    "document.querySelector('#nav-counter')?.textContent.trim() === '2 / 2'"
                )
                # HTMX carries the old class through its 20 ms settle phase.
                page.wait_for_function(
                    "!document.querySelector('#note-pill')?.classList.contains('ace-note-pill--has-note')"
                )

                # Prepare a return-to-A response while A still has its old
                # server text. Hold the HTML until the pending save commits.
                page.route("**/api/navigation", lambda route: serve(route, hold=True))
                page.evaluate("""() => {
                    void window.htmx.ajax('POST', '/api/navigation', {
                        target: 'body', swap: 'outerHTML',
                        values: {from_index: 1, to_index: 0, note_open: true,
                                 record_undo: false, history_mode: 'none'},
                    });
                }""")
                page.wait_for_timeout(100)
                assert len(held) == 1
                assert "Late old-source save" not in held[0][1].text
                page.evaluate("window.__lateNoteSave()")
                page.wait_for_function(
                    "window.__aceCurrentIndex === 1 && document.querySelector('#note-textarea')?.value === ''"
                )
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == "Late old-source save"
                assert not page.locator("#note-pill").evaluate(
                    "el => el.classList.contains('ace-note-pill--has-note')"
                )
                assert page.locator("#note-status").inner_text() != "Saved"

                route, response = held.pop()
                route.fulfill(
                    status=response.status_code,
                    headers=dict(response.headers), body=response.content,
                )
                page.wait_for_function(
                    "id => document.querySelector('#note-textarea')?.getAttribute('data-source-id') === id",
                    arg=first_id,
                )
                assert page.locator("#note-textarea").input_value() == "Late old-source save"
            finally:
                browser.close()
