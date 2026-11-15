"""A queued codebook import updates the live sidebar after an earlier swap."""

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
def test_queued_import_updates_live_sidebar(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "queued-import.ace"
    conn = create_project(str(project), "Queued import")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
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
                page.wait_for_function("window.AceHeadlessTreePreview?.getController?.()?.rootElement?.()")
                page.evaluate("""() => {
                    const open = XMLHttpRequest.prototype.open;
                    const send = XMLHttpRequest.prototype.send;
                    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                        const path = new URL(url, location.origin).pathname;
                        this.__holdKind = path === '/api/codes/folder' ? 'blocker'
                            : path === '/api/codes/import' ? 'import' : '';
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
                    document.addEventListener('htmx:afterRequest', event => {
                        if (event.detail?.requestConfig?.path === '/api/codes/import') {
                            window.__importFinished = true;
                        }
                    });
                    htmx.ajax('POST', '/api/codes/folder', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: { name: 'Blocking folder', current_index: 0 },
                    });
                }""")
                page.wait_for_function("window.__releaseMutation?.blocker !== undefined")
                page.evaluate("""() => {
                    window.__oldSidebar = document.getElementById('code-sidebar');
                    window.AceHeadlessTreePreview.getController().importCodes(
                        JSON.stringify([{
                            name: 'Imported code', colour: '#123456', group_name: '',
                        }]), 0, 'coding', ''
                    );
                }""")
                assert page.evaluate("Boolean(window.__releaseMutation?.import)") is False
                with page.expect_response("**/api/codes/folder", timeout=5000):
                    page.evaluate("window.__releaseMutation.blocker()")
                page.wait_for_function("""() =>
                    document.getElementById('code-sidebar') !== window.__oldSidebar &&
                    document.getElementById('ace-headless-tree-mount')?.dataset.aceTreeController === 'headless'
                """)
                page.wait_for_function("window.__releaseMutation?.import !== undefined")
                with page.expect_response("**/api/codes/import", timeout=5000):
                    page.evaluate("window.__releaseMutation.import()")
                page.wait_for_function("window.__importFinished === true")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Imported code'"
                    ).fetchone()[0] == 1
                imported_row = page.locator('.ace-ht-row[data-kind="code"]', has_text="Imported code")
                imported_row.wait_for(timeout=1000)
                assert imported_row.count() == 1
            finally:
                browser.close()
