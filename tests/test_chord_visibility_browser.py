"""Starting a chord shortcut keeps the whole codebook available."""

import sqlite3
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
def test_chord_mode_highlights_without_hiding_codes(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "chords.ace"
    conn = create_project(str(project), "Chord visibility")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "A sentence to code.", "row")
    for index in range(34):
        add_code(conn, f"Code {index + 1}", "#336699")
    empty_folder_id = add_folder(conn, "Empty folder")
    folder_id = add_folder(conn, "Chord folder")
    nested_code_id = add_code(conn, "Code 35", "#336699", parent_id=folder_id)
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
                assert codes.count() == 35
                page.locator(".ace-sentence").first.click()
                page.keyboard.press(";")
                assert page.evaluate("window.aceIsChordAwaiting()")
                assert codes.count() == 35
                chord_chip = page.locator(".ace-ht-chip--chord").first
                assert chord_chip.is_visible()
                assert chord_chip.evaluate("el => getComputedStyle(el).boxShadow") != "none"
                first_chord = page.locator(".ace-ht-row--code[data-chord]").first.get_attribute(
                    "data-chord"
                )
                chord_row = page.locator(f'.ace-ht-row--code[data-chord="{first_chord}"]')
                chord_code_id = chord_row.get_attribute("data-code-id")
                matched_chip = chord_row.locator(".ace-ht-chip--chord")
                page.evaluate("""() => {
                    window.__chordNotifications = [];
                    document.addEventListener("ace:chord-matches", event => {
                        window.__chordNotifications.push(event.detail.matches);
                    });
                }""")
                page.keyboard.press(first_chord[0])
                assert codes.count() == 35
                assert page.locator(".ace-ht-chip--chord.ace-chord-match").count() > 0
                assert "ace-chord-match" in matched_chip.get_attribute("class")
                initial_matches = page.locator(".ace-ht-chip--chord.ace-chord-match").count()
                assert page.evaluate("window.__chordNotifications") == [initial_matches]
                page.locator(
                    f'.ace-ht-row[data-folder-id="{empty_folder_id}"] .ace-ht-toggle'
                ).click()
                assert page.evaluate("window.__chordNotifications") == [initial_matches]
                page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                ).click()
                assert "ace-chord-match" in matched_chip.get_attribute("class")
                assert page.locator(".ace-ht-chip--chord.ace-chord-match").count() == initial_matches - 1
                assert f"{initial_matches - 1} visible matches" in page.locator(
                    "#ace-statusbar-event"
                ).inner_text()
                assert page.evaluate("window.__chordNotifications") == [initial_matches, initial_matches - 1]
                page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                ).click()
                assert page.evaluate("window.__chordNotifications") == [
                    initial_matches, initial_matches - 1, initial_matches
                ]
                nested_chord = page.locator(
                    f'.ace-ht-row--code[data-code-id="{nested_code_id}"]'
                ).get_attribute("data-chord")
                with page.expect_response("**/api/code/apply-sentence"):
                    page.keyboard.press(first_chord[1])
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT code_id FROM annotation WHERE deleted_at IS NULL"
                    ).fetchone()[0] == chord_code_id
                assert codes.count() == 35
                assert not page.evaluate("window.aceIsChordAwaiting()")

                page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                ).click()
                page.locator(".ace-sentence").first.click()
                page.keyboard.press(";")
                page.keyboard.press(nested_chord[0])
                with page.expect_response("**/api/code/apply-sentence", timeout=5000):
                    page.keyboard.press(nested_chord[1])
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT 1 FROM annotation WHERE code_id = ? AND deleted_at IS NULL",
                        (nested_code_id,),
                    ).fetchone()
                assert not page.evaluate("window.aceIsChordAwaiting()")
                page.locator(
                    f'.ace-ht-row[data-folder-id="{folder_id}"] .ace-ht-toggle'
                ).click()

                search = page.locator("#code-search-input")
                search.fill("Code 1")
                assert 0 < codes.count() < 35
                page.locator(".ace-sentence").first.click()
                page.keyboard.press(";")
                assert codes.count() == 35
                page.keyboard.press("Escape")
                assert 0 < codes.count() < 35
            finally:
                browser.close()
