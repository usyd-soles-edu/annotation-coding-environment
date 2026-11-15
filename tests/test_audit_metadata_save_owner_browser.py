"""Audit metadata saves only consume their own request results."""

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
def test_failed_sidebar_rename_does_not_fail_pending_audit_save(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "audit-save-owner.ace"
    conn = create_project(str(project), "Audit save owner")
    add_source(conn, "S1", "Some source text.", "row")
    alpha_id = add_code(conn, "Alpha", "#AA0000")
    add_code(conn, "Beta", "#0000AA")
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
                page.goto(f"http://127.0.0.1:8080/code/{alpha_id}/view")
                page.evaluate("""() => {
                    const open = XMLHttpRequest.prototype.open;
                    const send = XMLHttpRequest.prototype.send;
                    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                        this.__auditSavePath = new URL(url, location.origin).pathname;
                        return open.call(this, method, url, ...rest);
                    };
                    XMLHttpRequest.prototype.send = function (body) {
                        const requestId = body instanceof FormData
                            ? body.get('request_id')
                            : new URLSearchParams(body).get('request_id');
                        if (this.__auditSavePath.startsWith('/api/codes/')
                            && !requestId) {
                            window.__releaseSidebarRename = () => send.call(this, body);
                            return;
                        }
                        return send.call(this, body);
                    };
                }""")

                # Keep a tree rename pending, then queue a metadata save for
                # the same URL. The failed rename must not finish that save.
                row = page.locator(f'.ace-ht-row[data-item-id="{alpha_id}"]')
                row.focus()
                row.press("F2")
                rename = row.locator("input.ace-ht-rename")
                rename.fill("Beta")
                rename.press("Enter")
                page.wait_for_function("typeof window.__releaseSidebarRename === 'function'")

                page.locator("#cv-mode-edit").focus()
                page.keyboard.press("Enter")
                name = page.locator("#cv-code-name")
                name.fill("Alpha saved")
                name.press("Enter")

                with page.expect_response(f"**/api/codes/{alpha_id}") as failed_rename:
                    page.evaluate("window.__releaseSidebarRename()")
                assert "already exists" in failed_rename.value.text()
                page.wait_for_function(
                    "document.querySelector('.cv-code-name')?.textContent === 'Alpha saved'"
                )
                assert page.locator("#cv-code-name-error").is_hidden()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT name FROM codebook_code WHERE id = ?", (alpha_id,)
                    ).fetchone()[0] == "Alpha saved"

                # The editor must still report an error for its own request.
                page.route(
                    f"**/api/codes/{alpha_id}",
                    lambda route: route.fulfill(status=503, body="save failed"),
                    times=1,
                )
                name.fill("Alpha failed")
                with page.expect_response(f"**/api/codes/{alpha_id}") as failed_save:
                    name.press("Enter")
                assert failed_save.value.status == 503
                page.wait_for_function(
                    "!document.getElementById('cv-code-name-error')?.hidden"
                )
                assert "could not be saved" in page.locator(
                    "#cv-code-name-error"
                ).inner_text()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT name FROM codebook_code WHERE id = ?", (alpha_id,)
                    ).fetchone()[0] == "Alpha saved"
            finally:
                browser.close()
