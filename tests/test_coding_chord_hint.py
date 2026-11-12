"""Browser regression for the first two-letter code shortcut."""

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
def test_thirty_second_code_explains_chord_once(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "chords.ace"
    conn = create_project(str(project), "Chord test")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "A source for shortcuts.", "row")
    for index in range(31):
        add_code(conn, f"Code {index + 1}", "#336699")
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
                page.wait_for_function(
                    "document.querySelectorAll('.ace-ht-row--code').length === 31"
                )
                assert page.locator(".ace-statusbar-event").inner_text() == ""

                page.evaluate("""() => window.htmx.ajax('POST', '/api/codes', {
                    target: '#code-sidebar', swap: 'outerHTML',
                    values: {name: 'Code 32', current_index: 0}
                })""")
                page.wait_for_function(
                    "document.querySelectorAll('.ace-ht-row--code[data-chord]').length === 1"
                )
                assert "Codes after 31 use ; then the two letters" in page.locator(
                    ".ace-statusbar-event"
                ).inner_text()
                assert "then two letters" in page.locator(".ace-sidebar-legend").inner_text()
                chord_row = page.locator(".ace-ht-row--code[data-chord]").first
                assert chord_row.get_attribute("aria-description").startswith(
                    "Shortcut: press semicolon, then "
                )
                assert page.evaluate("localStorage.getItem('ace-chord-hint-seen')") == "1"

                page.reload()
                chord_row.wait_for()
                assert page.locator(".ace-statusbar-event").inner_text() == ""
            finally:
                browser.close()
