"""Flag and note markers remain visible in the corpus sparkline."""

import asyncio
import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.assignment import ensure_assignments, set_flagged
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.models.source_note import upsert_note


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_sparkline_shows_flag_and_note_positions(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "sparkline.ace"
    conn = create_project(str(project), "Sparkline")
    coder_id = list_coders(conn)[0]["id"]
    source_ids = [
        add_source(conn, f"S{i + 1}", f"Source {i + 1} text.", "row")
        for i in range(9)
    ]
    ensure_assignments(conn, coder_id)
    for index in (1, 6):
        set_flagged(conn, source_ids[index], coder_id, True)
    for index in (3, 6):
        upsert_note(conn, source_ids[index], coder_id, "Review this source")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 1000})

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
                page.goto("http://127.0.0.1:8080/code?index=0")
                spark = page.locator("#ace-grid-spark")
                assert spark.is_visible()
                flag_path = spark.locator(".spark-flag-ticks")
                note_path = spark.locator(".spark-note-ticks")
                assert flag_path.get_attribute("d").count("M") == 2
                assert note_path.get_attribute("d").count("M") == 2
                assert "2 flagged" in spark.get_attribute("aria-label")
                assert "2 with notes" in spark.get_attribute("aria-label")
                assert flag_path.evaluate("el => getComputedStyle(el).stroke") == "rgb(216, 67, 21)"
                assert note_path.evaluate("el => getComputedStyle(el).stroke") == "rgb(212, 160, 23)"

                positions = spark.evaluate("""el => {
                    const x = index => Math.round(2 + index / 8 * (el.clientWidth - 4));
                    return {flags: [x(1), x(6)], notes: [x(3), x(6)]};
                }""")
                for x in positions["flags"]:
                    assert f"M{x},27v6" in flag_path.get_attribute("d")
                for x in positions["notes"]:
                    assert f"M{x},34v5" in note_path.get_attribute("d")

                page.evaluate("window.aceOpenNoteRead(); window.aceEnterEditMode()")
                page.locator("#note-textarea").fill("A new note")
                page.wait_for_function(
                    "document.getElementById('ace-grid-spark').getAttribute('aria-label').includes('3 with notes')"
                )
                assert note_path.get_attribute("d").count("M") == 3
                page.locator("#note-textarea").fill("")
                page.wait_for_function(
                    "document.getElementById('ace-grid-spark').getAttribute('aria-label').includes('2 with notes')"
                )
                assert note_path.get_attribute("d").count("M") == 2
                page.evaluate("window.__flagTextPanel = document.getElementById('text-panel')")
                page.locator("#nav-flag-btn").click()
                page.wait_for_function(
                    "document.getElementById('ace-grid-spark').getAttribute('aria-label').includes('3 flagged')"
                )
                assert flag_path.get_attribute("d").count("M") == 3
                assert page.evaluate(
                    "document.getElementById('text-panel') === window.__flagTextPanel"
                )
                assert page.locator("#nav-flag-btn [data-flag-label]").inner_text() == "⚑ Flagged"

                # A very large corpus still produces at most one marker per
                # pixel column, rather than thousands of SVG elements.
                page.evaluate("""() => {
                    const data = Array.from({length: 3000}, (_, i) => ({
                        index: i, source_id: String(i), display_id: String(i),
                        count: 0, flagged: true, note: true,
                    }));
                    document.getElementById('ace-sources-data').textContent = JSON.stringify(data);
                    window._aceRenderSourceGrid();
                }""")
                assert flag_path.get_attribute("d").count("M") <= spark.evaluate("el => el.clientWidth")
                assert note_path.get_attribute("d").count("M") <= spark.evaluate("el => el.clientWidth")
                assert "3000 flagged" in spark.get_attribute("aria-label")
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_late_note_save_does_not_restore_old_marker(tmp_path, engine):
    async_api = pytest.importorskip("playwright.async_api")
    project = tmp_path / "note-race.ace"
    conn = create_project(str(project), "Note race")
    coder_id = list_coders(conn)[0]["id"]
    source_id = add_source(conn, "S1", "First source text.", "row")
    add_source(conn, "S2", "Second source text.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id

        async def exercise():
            first_started = asyncio.Event()
            release_first = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, engine).launch()
                try:
                    page = await browser.new_page(viewport={"width": 1280, "height": 1000})

                    async def serve_from_test_client(route):
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
                        if url.path.startswith("/api/source-note/") and request.post_data == "note_text=First":
                            first_started.set()
                            await release_first.wait()
                        await route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers), body=response.content,
                        )

                    await page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                    await page.goto("http://127.0.0.1:8080/code?index=0")
                    await page.evaluate("""() => {
                        window.__noteResponsesHandled = 0;
                        const original = window.fetch.bind(window);
                        window.fetch = (...args) => {
                            const response = original(...args);
                            if (String(args[0]).startsWith('/api/source-note/')) {
                                response.then(() => setTimeout(() => {
                                    window.__noteResponsesHandled++;
                                }, 0));
                            }
                            return response;
                        };
                        window.aceOpenNoteRead();
                        window.aceEnterEditMode();
                    }""")
                    textarea = page.locator("#note-textarea")
                    await textarea.fill("First")
                    await asyncio.wait_for(first_started.wait(), timeout=5)
                    await textarea.fill("")
                    await page.wait_for_function("window.__noteResponsesHandled === 1", timeout=5000)
                    release_first.set()
                    await page.wait_for_function("window.__noteResponsesHandled === 2", timeout=5000)
                    assert await page.locator(".spark-note-ticks").count() == 0
                    assert "0 with notes" in await page.locator("#ace-grid-spark").get_attribute("aria-label")
                    assert "ace-note-pill--has-note" not in await page.locator("#note-pill").get_attribute("class")
                    with sqlite3.connect(project) as stored:
                        assert stored.execute(
                            "SELECT COUNT(*) FROM source_note WHERE source_id = ? AND coder_id = ?",
                            (source_id, coder_id),
                        ).fetchone()[0] == 0
                finally:
                    release_first.set()
                    await browser.close()

        asyncio.run(exercise())
