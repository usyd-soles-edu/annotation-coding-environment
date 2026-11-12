"""Coding feedback has one live announcer and an accessible visual receipt."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_coding_receipt_does_not_duplicate_live_announcements(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "announcements.ace"
    conn = create_project(str(project), "Announcements")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "First", "A source to code.", "row")
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
                page.goto("http://127.0.0.1:8080/code")
                receipt = page.locator("#ace-notification-receipt")

                def assert_visual_only():
                    assert receipt.get_attribute("aria-live") is None
                    assert receipt.get_attribute("role") is None
                    assert receipt.get_attribute("aria-hidden") is None

                assert_visual_only()
                page.evaluate("window._setStatus('Saved locally', 'ok-sticky')")
                assert receipt.inner_text() == "Saved locally"
                assert page.locator("#ace-live-region").inner_text() == "Saved locally"
                assert_visual_only()

                page.evaluate("""() => htmx.ajax('POST', '/api/codes', {
                    target: '#text-panel', swap: 'none',
                    values: {name: ' ', current_index: 0}
                })""")
                page.wait_for_function(
                    "document.querySelector('#ace-notification-receipt').textContent === 'Code name cannot be empty.'"
                )
                assert page.locator("#ace-live-region-assertive").inner_text() == "Code name cannot be empty."
                assert_visual_only()

                page.evaluate("""() => htmx.ajax('POST', '/api/undo', {
                    target: '#text-panel', swap: 'outerHTML', values: {current_index: 0}
                })""")
                page.wait_for_function(
                    "document.querySelector('#ace-notification-receipt').textContent === 'Nothing to undo'"
                )
                assert page.locator("#ace-live-region").inner_text() == "Nothing to undo"
                assert_visual_only()
            finally:
                browser.close()
