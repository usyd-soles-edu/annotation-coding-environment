"""Browser regression for in-place source navigation."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.models.source_note import upsert_note


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_source_navigation_keeps_page_and_note_drawer(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "navigation.ace"
    conn = create_project(str(project), "Navigation")
    coder_id = list_coders(conn)[0]["id"]
    first_id = add_source(conn, "S1", "First source for navigation.", "row")
    second_id = add_source(conn, "S2", "Second source for navigation.", "row")
    add_source(conn, "S3", "Third source for navigation.", "row")
    add_code(conn, "Example", "#336699")
    upsert_note(conn, second_id, coder_id, "Second source note")
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
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator(".ace-sentence").first.click()
                page.evaluate("window.__navigationMarker = 1")
                page.keyboard.press("n")
                assert page.evaluate("window.aceIsNoteDrawerOpen()")
                page.keyboard.press("n")
                page.locator("#note-textarea").fill("First source note")
                page.evaluate("""() => {
                    window.__aceLastSelection = {start: 0, end: 5, text: 'First'};
                    const range = document.createRange();
                    const text = document.querySelector('.ace-sentence').firstChild;
                    range.setStart(text, 0);
                    range.setEnd(text, 5);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(range);
                    const original = window.htmx.ajax.bind(window.htmx);
                    window.htmx.ajax = (method, url, options) => {
                        if (url === '/api/navigation' && window.__holdNextNavigation) {
                            window.__holdNextNavigation = false;
                            return new Promise(resolve => {
                                window.__releaseNavigation = () => resolve(original(method, url, options));
                            });
                        }
                        return original(method, url, options);
                    };
                    window.__holdNextNavigation = true;
                }""")

                page.evaluate("window.aceNavigateNext()")
                page.wait_for_function("typeof window.__releaseNavigation === 'function'")
                assert page.locator("#note-textarea").evaluate("el => el.readOnly")
                page.locator("#note-textarea").press("x")
                assert page.locator("#note-textarea").input_value() == "First source note"
                page.evaluate("window.__releaseNavigation(); delete window.__releaseNavigation")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                assert "Second source for navigation." in page.locator("#text-panel").inner_text()
                assert page.url.endswith("/code?index=1")
                assert page.evaluate("window.__navigationMarker") == 1
                assert page.locator("#note-textarea").input_value() == "Second source note"
                assert page.locator("#note-drawer").get_attribute("aria-hidden") == "false"
                assert page.locator("#note-textarea").is_enabled()
                assert not page.locator("#note-textarea").evaluate("el => el.readOnly")
                assert page.evaluate("window.__aceLastSelection === null")
                assert page.evaluate("window.getSelection().toString()") == ""
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (first_id,)
                    ).fetchone()[0] == "First source note"
                    assert stored.execute(
                        "SELECT note_text FROM source_note WHERE source_id = ?", (second_id,)
                    ).fetchone()[0] == "Second source note"

                page.locator(".ace-sentence").first.click()
                with page.expect_response("**/api/code/apply-sentence", timeout=5000):
                    page.keyboard.press("1")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT selected_text FROM annotation WHERE source_id = ? AND deleted_at IS NULL",
                        (second_id,),
                    ).fetchone()[0] == "Second source for navigation."

                page.evaluate("window.__holdNextNavigation = true; window.aceNavigateNext()")
                page.wait_for_function("typeof window.__releaseNavigation === 'function'")
                page.go_back()
                page.evaluate("window.__releaseNavigation(); delete window.__releaseNavigation")
                page.wait_for_function("window.__aceCurrentIndex === 0")
                assert "First source for navigation." in page.locator("#text-panel").inner_text()
                assert page.url.endswith("/code?index=0")
                assert page.locator("#note-textarea").input_value() == "First source note"
                assert page.evaluate("window.__navigationMarker") == 1
                assert not page.evaluate("window.aceIsNoteDrawerOpen()")

                page.locator("#text-panel").click()
                page.keyboard.press("Shift+ArrowRight")
                page.keyboard.press("Shift+ArrowRight")
                page.wait_for_function("window.__aceCurrentIndex === 2")
                assert "Third source for navigation." in page.locator("#text-panel").inner_text()
                assert page.evaluate("window.__navigationMarker") == 1

                def fail_navigation(route):
                    route.fulfill(status=500, body="controlled navigation failure")

                page.route("**/api/navigation", fail_navigation)
                with page.expect_response("**/api/navigation", timeout=5000):
                    page.evaluate("window.aceNavigate(1)")
                page.wait_for_function("!document.body.dataset.aceNavigating")
                assert page.evaluate("window.__aceCurrentIndex") == 2
                assert page.url.endswith("/code?index=2")
                assert "Source navigation failed" in page.locator(
                    ".ace-statusbar-event"
                ).inner_text()

                with page.expect_response("**/api/navigation", timeout=5000):
                    page.go_back()
                page.wait_for_function("!document.body.dataset.aceNavigating")
                assert page.evaluate("window.__aceCurrentIndex") == 2
                assert page.url.endswith("/code?index=2")
                assert "Third source for navigation." in page.locator("#text-panel").inner_text()
                page.unroute("**/api/navigation", fail_navigation)
            finally:
                browser.close()
