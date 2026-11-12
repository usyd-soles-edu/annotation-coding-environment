"""Coding and audit share accessible codebook sidebar resizing."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_sidebar_resize_is_shared_between_coding_and_audit(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "resize.ace"
    conn = create_project(str(project), "Resize")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    code_id = add_code(conn, "Example", "#336699")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            try:
                browser = getattr(playwright, browser_name).launch()
            except sync_api.Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip(f"Playwright {browser_name} is not installed")
                raise
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
                coding_handle = page.get_by_role("separator", name="Resize codebook sidebar")
                coding_handle.focus()
                coding_handle.press("ArrowRight")
                assert coding_handle.get_attribute("aria-valuenow") == "384"
                assert page.evaluate("localStorage.getItem('ace-sidebar-width')") == "384"

                page.goto(f"http://127.0.0.1:8080/code/{code_id}/view")
                audit_handle = page.get_by_role("separator", name="Resize codebook sidebar")
                assert audit_handle.get_attribute("tabindex") == "0"
                assert audit_handle.get_attribute("aria-valuenow") == "384"
                audit_handle.focus()
                audit_handle.press("ArrowRight")
                assert audit_handle.get_attribute("aria-valuenow") == "408"
                audit_handle.press("Home")
                assert audit_handle.get_attribute("aria-valuenow") == "150"
                audit_handle.press("End")
                assert audit_handle.get_attribute("aria-valuenow") == "512"
                audit_handle.dblclick()
                assert audit_handle.get_attribute("aria-valuenow") == "360"
                assert page.evaluate("localStorage.getItem('ace-sidebar-width')") is None

                box = audit_handle.bounding_box()
                assert box is not None
                y = box["y"] + box["height"] / 2
                page.mouse.move(box["x"] + box["width"] / 2, y)
                page.mouse.down()
                page.mouse.move(440, y, steps=5)
                page.mouse.up()
                assert 430 <= int(audit_handle.get_attribute("aria-valuenow")) <= 450

                saved_width = int(page.evaluate("localStorage.getItem('ace-sidebar-width')"))
                page.set_viewport_size({"width": 1000, "height": 800})
                page.wait_for_function(
                    "document.getElementById('cv-resize-handle').getAttribute('aria-valuenow') === '400'"
                )
                assert int(page.evaluate("localStorage.getItem('ace-sidebar-width')")) == saved_width
                page.set_viewport_size({"width": 1280, "height": 800})
                page.wait_for_function(
                    "width => document.getElementById('cv-resize-handle').getAttribute('aria-valuenow') === String(width)",
                    arg=saved_width,
                )

                page.goto("http://127.0.0.1:8080/code")
                coding_handle = page.get_by_role("separator", name="Resize codebook sidebar")
                assert coding_handle.get_attribute("aria-valuenow") == str(saved_width)
            finally:
                browser.close()
