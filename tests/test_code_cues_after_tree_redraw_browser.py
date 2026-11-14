"""Code suggestions remain visible when the codebook tree redraws."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_code_cue_survives_folder_redraw(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "cues.ace"
    conn = create_project(str(project), "Code cues")
    coder_id = list_coders(conn)[0]["id"]
    add_source(
        conn, "Sample",
        "I revised my assessment after reading the tutor feedback comments. "
        "We planned lunch today.",
        "row",
    )
    feedback = add_code(
        conn, "Feedback uptake", "#3366cc",
        definition="Uses feedback comments to revise assessment work.",
    )
    folder_id = add_folder(conn, "Other folder")
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
                row = page.locator(f'.ace-ht-row--code[data-code-id="{feedback}"]')
                row.wait_for()
                page.evaluate("window.ACE_PREFS.set('ace-codebook-cues-enabled', '1')")
                with page.expect_response("**/api/code-cues"):
                    page.locator(".ace-sentence").first.click()
                page.wait_for_function(
                    "id => document.querySelector(`[data-code-id='${id}']`)"
                    ".classList.contains('ace-ht-row--cue')",
                    arg=feedback,
                )
                search = page.locator("#code-search-input")
                search.fill("Feedback")
                assert "ace-ht-row--cue" not in row.get_attribute("class")
                with page.expect_response("**/api/code-cues", timeout=5000):
                    search.press("Escape")
                page.wait_for_function(
                    "id => document.querySelector(`[data-code-id='${id}']`)"
                    ".classList.contains('ace-ht-row--cue')",
                    arg=feedback,
                )
                page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                ).click()
                assert "ace-ht-row--cue" in row.get_attribute("class")
                with page.expect_response("**/api/code-cues"):
                    page.locator(".ace-sentence").nth(1).click()
                assert "ace-ht-row--cue" not in row.get_attribute("class")
                with page.expect_response("**/api/code-cues"):
                    page.locator(".ace-sentence").first.click()
                page.wait_for_function(
                    "id => document.querySelector(`[data-code-id='${id}']`)"
                    ".classList.contains('ace-ht-row--cue')",
                    arg=feedback,
                )
            finally:
                browser.close()
