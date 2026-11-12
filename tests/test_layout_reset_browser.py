"""The visible layout reset restores both persisted panel sizes."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_visible_layout_reset_restores_panel_sizes(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "layout-reset.ace"
    conn = create_project(str(project), "Layout reset")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "First", "First source.", "row")
    add_source(conn, "Second", "Second source.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, browser_name).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})

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
                page.evaluate("""() => {
                    localStorage.setItem('ace-sidebar-width', '420');
                    localStorage.setItem('ace-grid-height', '35vh');
                }""")
                page.reload()
                reset = page.get_by_role("button", name="Reset panel sizes")
                assert reset.is_visible()
                assert page.locator("#resize-handle").get_attribute("aria-valuenow") == "420"
                assert page.locator(".ace-sidebar-vsplit").get_attribute("aria-valuenow") == "35"

                # Code creation replaces the sidebar, including its reset
                # button and source-map resize handle.
                page.locator("#code-search-input").fill("Theme")
                page.locator("#code-search-input").press("Enter")
                page.locator(".ace-ht-row--code").first.wait_for()

                reset.click()
                assert page.locator("#resize-handle").get_attribute("aria-valuenow") == "360"
                assert page.locator(".ace-sidebar-vsplit").get_attribute("aria-valuenow") == "18"
                assert page.evaluate("localStorage.getItem('ace-sidebar-width')") is None
                assert page.evaluate("localStorage.getItem('ace-grid-height')") is None
                page.reload()
                assert page.locator("#resize-handle").get_attribute("aria-valuenow") == "360"
                assert page.locator(".ace-sidebar-vsplit").get_attribute("aria-valuenow") == "18"
            finally:
                browser.close()
