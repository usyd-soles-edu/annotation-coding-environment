"""Browser regression for the coding shortcut dialog and its focus behaviour."""

import sqlite3
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
def test_coding_shortcuts_are_modal_and_restore_focus(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "shortcuts.ace"
    conn = create_project(str(project), "Shortcuts")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "A source to code.", "row")
    for index in range(32):
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
                source = page.locator(".ace-sentence").first
                source.click()
                dialog = page.get_by_role("dialog", name="Keyboard shortcuts")
                assert not dialog.is_visible()
                page.keyboard.press("?")
                assert dialog.is_visible()
                assert dialog.evaluate("el => el.matches(':modal')")
                assert "Focus codebook search" in dialog.inner_text()
                assert "View coded text" in dialog.inner_text()
                page.keyboard.press("v")
                assert page.url.endswith("/code")
                chord = page.locator(".ace-ht-row--code[data-chord]").first.get_attribute(
                    "data-chord"
                )
                page.keyboard.press(";")
                assert not page.evaluate("window.aceIsChordAwaiting()")
                for letter in chord:
                    page.keyboard.press(letter)
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
                    ).fetchone()[0] == 0
                page.keyboard.press("Escape")
                assert not dialog.is_visible()

                menu = page.locator("#codebook-menu-btn")
                menu.click()
                page.locator("#codebook-menu-shortcuts-btn").click()
                assert dialog.is_visible()
                dialog.get_by_role("button", name="Close").click()
                assert not dialog.is_visible()
                assert menu.evaluate("el => document.activeElement === el")

                source.click()
                page.keyboard.press("n")
                assert page.evaluate("window.aceIsNoteDrawerOpen()")
                page.keyboard.press("?")
                assert dialog.is_visible()
                page.keyboard.press("Escape")
                assert not dialog.is_visible()
                assert page.evaluate("window.aceIsNoteDrawerOpen()")
                page.keyboard.press("Escape")
                assert not page.evaluate("window.aceIsNoteDrawerOpen()")
            finally:
                browser.close()
