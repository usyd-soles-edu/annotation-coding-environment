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


def _highlight_geometry(tmp_path, engine, text, *, fractional_line_height=False):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "long-highlight.ace"
    conn = create_project(str(project), "Long highlight")
    coder_id = list_coders(conn)[0]["id"]
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
                    "expected => document.querySelectorAll(expected).length >= 1",
                    arg=f"#ace-hl-overlay rect.ace-hl-{code_id}",
                )
                if fractional_line_height:
                    page.locator(".ace-text-body").evaluate(
                        "el => el.style.lineHeight = '35.5px'"
                    )
                    page.evaluate(
                        "() => new Promise(resolve => requestAnimationFrame(() => "
                        "requestAnimationFrame(() => requestAnimationFrame(resolve))))"
                    )
                geometry = rects.evaluate_all("""elements => elements.map(el => ({
                    y: Number(el.getAttribute('y')),
                    width: Number(el.getAttribute('width')),
                    height: Number(el.getAttribute('height')),
                }))""")
                return geometry
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_long_cross_paragraph_highlight_has_no_block_rectangles(tmp_path, engine):
    text = "\n\n".join(f"Short sentence {i}." for i in range(150))
    geometry = _highlight_geometry(tmp_path, engine, text)

    assert len(geometry) == 150
    assert all(0 < rect["width"] < 300 for rect in geometry)
    assert all(0 < rect["height"] <= 40 for rect in geometry)


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_wrapped_highlight_fills_line_gaps_but_keeps_paragraph_break(tmp_path, engine):
    text = ("A long sentence with enough words to wrap across the reading column. " * 5).strip()
    text += "\n\nA separate paragraph."
    geometry = _highlight_geometry(tmp_path, engine, text, fractional_line_height=True)
    gaps = [next_rect["y"] - rect["y"] - rect["height"]
            for rect, next_rect in zip(geometry, geometry[1:])]

    assert len(geometry) >= 5
    assert len([gap for gap in gaps if gap > 1]) == 1
    assert max(gaps) >= 10
    assert all(gap == 0 for gap in gaps if gap != max(gaps)), gaps
