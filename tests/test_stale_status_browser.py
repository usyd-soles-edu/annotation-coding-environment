"""A successful coding action clears an older sticky error."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_successful_navigation_clears_stale_error(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "stale-status.ace"
    conn = create_project(str(project), "Status")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "First source.", "row")
    add_source(conn, "S2", "Second source.", "row")
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
                        request.method, path, content=request.post_data_buffer, headers=headers
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers),
                        body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.evaluate("window._setStatus('Old validation error', 'err')")
                assert page.locator(".ace-statusbar-event--err").inner_text() == "Old validation error"

                page.evaluate("window.aceNavigateNext()")
                page.wait_for_function(
                    "window.__aceCurrentIndex === 1 && !document.body.dataset.aceNavigating"
                )
                assert page.locator(".ace-statusbar-event").inner_text() == ""
                assert page.locator("#ace-notification-receipt").inner_text() == ""

                page.evaluate("""() => {
                    window.__statusSettleCount = 0;
                    document.addEventListener('htmx:afterSettle', () => window.__statusSettleCount++);
                    htmx.ajax('POST', '/api/codes', {
                        target: '#text-panel', swap: 'none',
                        values: {name: ' ', current_index: 1}
                    });
                }""")
                page.wait_for_function("window.__statusSettleCount >= 3")
                assert page.locator(".ace-statusbar-event--err").inner_text() == "Code name cannot be empty."
                assert page.locator("#ace-notification-receipt").inner_text() == "Code name cannot be empty."

                page.evaluate("window._setStatus('Another old error', 'err')")
                page.locator("#nav-flag-btn").click()
                page.wait_for_function(
                    "document.querySelector('#nav-flag-btn').getAttribute('aria-pressed') === 'true'"
                )
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event').textContent === ''"
                )
                assert page.locator(".ace-statusbar-event").inner_text() == ""
                assert page.locator("#ace-notification-receipt").inner_text() == ""

                # An earlier action may still be settling when a later
                # response replaces the status with a fresh error.
                page.evaluate("""() => {
                    htmx.config.defaultSettleDelay = 600;
                    window.__overlapSettles = 0;
                    document.addEventListener('htmx:afterSettle', () => window.__overlapSettles++);
                }""")
                page.locator("#nav-flag-btn").click()
                page.wait_for_function(
                    "document.querySelector('#nav-flag-btn').getAttribute('aria-pressed') === 'false'"
                )
                assert page.evaluate("window.__overlapSettles") == 0
                page.evaluate("""() => htmx.ajax('POST', '/api/codes', {
                    target: '#text-panel', swap: 'none',
                    values: {name: ' ', current_index: 1}
                })""")
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event').textContent === 'Code name cannot be empty.'"
                )
                assert page.evaluate("window.__overlapSettles") == 0
                page.wait_for_function("window.__overlapSettles >= 4")
                assert page.locator(".ace-statusbar-event--err").inner_text() == "Code name cannot be empty."
            finally:
                browser.close()
