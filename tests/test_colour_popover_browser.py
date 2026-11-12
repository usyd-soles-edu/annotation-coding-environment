"""The codebook colour picker stays usable at the edge of the viewport."""

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
def test_colour_popover_flips_into_viewport(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "colour.ace"
    conn = create_project(str(project), "Colour picker")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "A sentence.", "row")
    for index in range(50):
        add_code(conn, f"Code {index + 1}", "#336699")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 800, "height": 600})

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
                row = page.locator(".ace-ht-row--code").last
                row.click(button="right")
                page.get_by_role("menuitem", name="Change colour…").click()
                popover = page.locator(".ace-colour-popover")
                popover.wait_for()
                box = popover.bounding_box()
                assert box is not None
                assert box["x"] >= 0 and box["x"] + box["width"] <= 800
                assert box["y"] >= 0 and box["y"] + box["height"] <= 600
                first_swatch = popover.locator("button").first
                assert first_swatch.get_attribute("aria-label").startswith("Set code colour to #")
                assert first_swatch.evaluate("el => document.activeElement === el")
                assert first_swatch.evaluate("el => getComputedStyle(el).outlineWidth") == "2px"
                page.keyboard.press("Escape")
                assert popover.count() == 0
                assert row.evaluate("el => document.activeElement === el")
            finally:
                browser.close()
