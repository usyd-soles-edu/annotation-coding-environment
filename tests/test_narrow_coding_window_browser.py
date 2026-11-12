"""Narrow coding windows expose both sides of the fixed-width workspace."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_narrow_window_can_reach_applied_codes_and_codebook(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "narrow.ace"
    conn = create_project(str(project), "Narrow")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, browser_name).launch()
            try:
                page = browser.new_page(viewport={"width": 800, "height": 700})

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

                pan = page.get_by_role("button", name="Show applied codes panel")
                assert pan.is_visible()
                assert page.evaluate("document.activeElement?.id") == "text-panel"
                page.keyboard.press("Tab")
                assert pan.evaluate("el => document.activeElement === el")
                page.keyboard.press("Tab")
                assert page.evaluate("document.activeElement?.id") == "code-search-input"
                page.keyboard.press("Shift+Tab")
                assert pan.evaluate("el => document.activeElement === el")
                page.keyboard.press("Enter")
                page.wait_for_function(
                    "document.querySelector('.ace-right-inspector').getBoundingClientRect().right <= innerWidth"
                )
                assert page.get_by_role("button", name="Show codebook panel").is_visible()

                page.get_by_role("button", name="Show codebook panel").click()
                page.wait_for_function("window.scrollX === 0")
                assert page.locator("#code-sidebar").bounding_box()["x"] == 0

                page.locator("#note-pill").click()
                page.get_by_role("button", name="Show applied codes panel").click()
                assert page.locator("#note-drawer").get_attribute("aria-hidden") == "false"
                page.wait_for_function(
                    "document.querySelector('#note-drawer').getBoundingClientRect().right <= innerWidth"
                )

                page.evaluate("window.aceCloseNote()")
                page.set_viewport_size({"width": 320, "height": 700})
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_function(
                    "scrollX === 0 && document.querySelector('#ace-narrow-pan')?.getAttribute('aria-label') === 'Show applied codes panel'"
                )
                pan_box = page.locator("#ace-narrow-pan").bounding_box()
                sidebar_box = page.locator("#code-sidebar").bounding_box()
                assert pan_box["x"] >= sidebar_box["x"] + sidebar_box["width"]
                page.locator("#ace-narrow-pan").click()
                page.wait_for_function(
                    "document.querySelector('.ace-right-inspector').getBoundingClientRect().right <= innerWidth"
                )
                pan_box = page.locator("#ace-narrow-pan").bounding_box()
                heading_box = page.locator(".ace-applied-codes-kicker").bounding_box()
                toggle_box = page.locator(".ace-applied-codes-toggle").bounding_box()
                assert pan_box["y"] + pan_box["height"] <= heading_box["y"]
                assert pan_box["x"] + pan_box["width"] <= toggle_box["x"]

                page.evaluate("window.aceOpenNoteRead()")
                page.wait_for_function(
                    "document.querySelector('#note-drawer').getBoundingClientRect().right <= innerWidth"
                )
                note_heading = page.locator("#note-drawer-title").bounding_box()
                assert pan_box["y"] + pan_box["height"] <= note_heading["y"]
                page.evaluate("window.aceCloseNote()")

                page.set_viewport_size({"width": 1280, "height": 700})
                assert not page.locator("#ace-narrow-pan").is_visible()
                page.locator("#text-panel").focus()
                page.keyboard.press("Tab")
                assert page.evaluate("document.activeElement?.id") == "code-search-input"
            finally:
                browser.close()
