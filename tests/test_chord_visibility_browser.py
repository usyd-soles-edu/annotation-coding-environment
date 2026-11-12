"""Starting a chord shortcut keeps the whole codebook available."""

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
def test_chord_mode_highlights_without_hiding_codes(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "chords.ace"
    conn = create_project(str(project), "Chord visibility")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "A sentence to code.", "row")
    for index in range(34):
        add_code(conn, f"Code {index + 1}", "#336699")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
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
                codes = page.locator(".ace-ht-row--code")
                codes.first.wait_for()
                assert codes.count() == 34
                page.locator(".ace-sentence").first.click()
                page.keyboard.press(";")
                assert page.evaluate("window.aceIsChordAwaiting()")
                assert codes.count() == 34
                chord_chip = page.locator(".ace-ht-chip--chord").first
                assert chord_chip.is_visible()
                assert chord_chip.evaluate("el => getComputedStyle(el).boxShadow") != "none"
                first_chord = page.locator(".ace-ht-row--code[data-chord]").first.get_attribute(
                    "data-chord"
                )
                page.keyboard.press(first_chord[0])
                assert codes.count() == 34
                assert page.locator(".ace-ht-chip--chord.ace-chord-match").count() > 0
                page.keyboard.press("Escape")
                assert codes.count() == 34
                assert not page.evaluate("window.aceIsChordAwaiting()")

                search = page.locator("#code-search-input")
                search.fill("Code 1")
                assert 0 < codes.count() < 34
                page.locator(".ace-sentence").first.click()
                page.keyboard.press(";")
                assert codes.count() == 34
                page.keyboard.press("Escape")
                assert 0 < codes.count() < 34
            finally:
                browser.close()
