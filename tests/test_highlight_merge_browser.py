"""Long cross-paragraph highlights stay on text lines in every web engine."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_long_cross_paragraph_highlight_has_no_block_rectangles(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "long-highlight.ace"
    conn = create_project(str(project), "Long highlight")
    coder_id = list_coders(conn)[0]["id"]
    text = "\n\n".join(f"Short sentence {i}." for i in range(150))
    source_id = add_source(conn, "S1", text, "row")
    code_id = add_code(conn, "Example", "#336699")
    add_annotation(conn, source_id, coder_id, code_id, 0, len(text), text)
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
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
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto("http://127.0.0.1:8080/code")
                rects = page.locator(f"#ace-hl-overlay rect.ace-hl-{code_id}")
                page.wait_for_function(
                    "expected => document.querySelectorAll(expected).length >= 150",
                    arg=f"#ace-hl-overlay rect.ace-hl-{code_id}",
                )
                geometry = rects.evaluate_all("""elements => elements.map(el => ({
                    width: Number(el.getAttribute('width')),
                    height: Number(el.getAttribute('height')),
                }))""")
                assert len(geometry) == 150
                assert all(0 < rect["width"] < 300 for rect in geometry)
                assert all(0 < rect["height"] <= 40 for rect in geometry)
            finally:
                browser.close()
