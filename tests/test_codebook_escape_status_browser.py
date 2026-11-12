"""The codebook Escape cascade confirms each completed step."""

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
def test_codebook_escape_status_steps(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "escape.ace"
    conn = create_project(str(project), "Escape status")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
    add_code(conn, "Beta", "#993366")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()

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
                search = page.locator("#code-search-input")
                search.fill("Alpha")
                row = page.locator('.ace-ht-row[data-kind="code"]').first
                row.click()
                page.keyboard.press("Meta+x")

                page.keyboard.press("Escape")
                assert page.locator(".ace-statusbar-event").text_content() == "Cut cleared"
                assert row.evaluate("el => document.activeElement === el")
                assert search.input_value() == "Alpha"

                page.keyboard.press("Escape")
                assert page.locator(".ace-statusbar-event").text_content() == "Filter cleared"
                assert row.evaluate("el => document.activeElement === el")
                assert search.input_value() == ""

                page.keyboard.press("Escape")
                assert page.locator(".ace-statusbar-event").text_content() == "Source focused"
                assert page.locator("#text-panel").evaluate("el => document.activeElement === el")

                search.fill("Beta")
                page.keyboard.press("Escape")
                assert page.locator(".ace-statusbar-event").text_content() == "Filter cleared"
                assert search.input_value() == ""
                assert search.evaluate("el => document.activeElement === el")
                page.keyboard.press("Escape")
                assert page.locator(".ace-statusbar-event").text_content() == "Source focused"
                assert page.locator("#text-panel").evaluate("el => document.activeElement === el")

                page.goto(f"http://127.0.0.1:8080/code/{code_id}/view")
                audit_search = page.locator("#code-search-input")
                audit_search.focus()
                page.keyboard.press("Escape")
                assert audit_search.evaluate("el => document.activeElement === el")
                assert page.locator(".ace-statusbar-event").text_content() != "Source focused"
            finally:
                browser.close()
