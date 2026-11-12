"""Browser regression for in-place source navigation."""

import asyncio
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
                page.locator("#text-panel").focus()
                page.keyboard.press("1")
                search = page.locator("#code-search-input")
                search.fill("Blocked folder")
                search.press("Shift+Enter")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
                    ).fetchone()[0] == 0
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE kind = 'folder' AND deleted_at IS NULL"
                    ).fetchone()[0] == 0
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

                search.fill("")
                page.wait_for_function(
                    "document.querySelector('.ace-ht-row--code .ace-ht-chip:not(.ace-ht-chip--chord)')?.textContent.trim() === '1'"
                )
                page.locator(".ace-sentence").first.click()
                with page.expect_response("**/api/code/apply-sentence", timeout=5000):
                    page.keyboard.press("1")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT selected_text FROM annotation WHERE source_id = ? AND deleted_at IS NULL",
                        (second_id,),
                    ).fetchone()[0] == "Second source for navigation."

                with page.expect_response("**/api/code/delete-sentence", timeout=5000):
                    page.keyboard.press("x")
                page.locator(".ace-statusbar-undo[data-ace-undo-affordance]").first.wait_for()

                page.evaluate("window.__holdNextNavigation = true; window.aceNavigateNext()")
                page.wait_for_function("typeof window.__releaseNavigation === 'function'")
                page.evaluate("document.querySelector('.ace-statusbar-undo[data-ace-undo-affordance]').click()")
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM annotation WHERE source_id = ? AND deleted_at IS NULL",
                        (second_id,),
                    ).fetchone()[0] == 0
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

                # A code request can still be in HTMX's body queue when
                # navigation is issued. Navigation must wait for its own
                # response and settle rather than the queue's early promise.
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator(".ace-sentence").first.click()
                page.evaluate("""() => {
                    const codeId = document.querySelector('.ace-ht-row--code').dataset.codeId;
                    document.dispatchEvent(new CustomEvent('ace:apply-code', {
                        detail: {codeId}
                    }));
                    window.aceNavigateNext();
                }""")
                page.wait_for_function(
                    "window.__aceCurrentIndex === 1 && !document.body.dataset.aceNavigating"
                )
                assert "Second source for navigation." in page.locator("#text-panel").inner_text()
                assert "Source navigation failed" not in page.locator(
                    ".ace-statusbar-event"
                ).inner_text()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM annotation WHERE source_id = ? AND deleted_at IS NULL",
                        (first_id,),
                    ).fetchone()[0] == 1

                # A queued navigation must also unlock the UI if its XHR
                # fails before responseURL is available.
                page.route("**/api/navigation", lambda route: route.abort())
                page.locator(".ace-sentence").first.click()
                page.evaluate("""() => {
                    const codeId = document.querySelector('.ace-ht-row--code').dataset.codeId;
                    document.dispatchEvent(new CustomEvent('ace:apply-code', {
                        detail: {codeId}
                    }));
                    window.aceNavigateNext();
                }""")
                page.wait_for_function("!document.body.dataset.aceNavigating", timeout=5000)
                assert page.evaluate("window.__aceCurrentIndex") == 1
                assert "Source navigation failed" in page.locator(
                    ".ace-statusbar-event"
                ).inner_text()
                assert not page.locator("#note-textarea").evaluate("el => el.readOnly")
                page.unroute("**/api/navigation")

                # A picker opened before navigation must recheck the editing
                # guard when its swatch is selected.
                code_row = page.locator(".ace-ht-row--code").first
                code_id = code_row.get_attribute("data-code-id")
                code_row.click(button="right")
                page.get_by_role("menuitem", name="Change colour…").click()
                palette = page.get_by_role("group", name="Change code colour")
                palette.wait_for()
                page.evaluate("""() => {
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
                    window.aceNavigateNext();
                }""")
                page.wait_for_function("typeof window.__releaseNavigation === 'function'")
                palette.get_by_role("button", name="Set code colour to #0B4F8A").click()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT colour FROM codebook_code WHERE id = ?", (code_id,)
                    ).fetchone()[0] == "#336699"
                page.evaluate("window.__releaseNavigation(); delete window.__releaseNavigation")
                page.wait_for_function("window.__aceCurrentIndex === 2 && !document.body.dataset.aceNavigating")

                # Mouse navigation should keep a note opened in READ mode
                # bound to the newly selected source too.
                page.goto("http://127.0.0.1:8080/code?index=0")
                page.locator("#note-pill").click()
                assert page.locator("#note-drawer").get_attribute("aria-hidden") == "false"
                page.locator("#btn-next").click()
                page.wait_for_function("window.__aceCurrentIndex === 1")
                assert page.locator("#note-drawer").get_attribute("aria-hidden") == "false"
                page.locator('.ace-grid-tile[data-source-index="2"]').click()
                page.wait_for_function("window.__aceCurrentIndex === 2")
                assert page.locator("#note-drawer").get_attribute("aria-hidden") == "false"
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("flag_response_first,flag_clicks", [
    (False, 1), (True, 1), (False, 2),
])
def test_flag_and_navigation_responses_keep_source_consistent(
    tmp_path, browser_name, flag_response_first, flag_clicks
):
    async_api = pytest.importorskip("playwright.async_api")
    project = tmp_path / "late-flag.ace"
    conn = create_project(str(project), "Late flag")
    coder_id = list_coders(conn)[0]["id"]
    first_id = add_source(conn, "S1", "First source text.", "row")
    second_id = add_source(conn, "S2", "Second source text.", "row")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id

        async def exercise():
            flag_started = asyncio.Event()
            release_flag = asyncio.Event()
            navigation_started = asyncio.Event()
            release_navigation = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, browser_name).launch()
                try:
                    page = await browser.new_page()

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
                        if url.path == "/api/code/flag":
                            flag_started.set()
                            await release_flag.wait()
                        if url.path == "/api/navigation" and flag_response_first:
                            navigation_started.set()
                            await release_navigation.wait()
                        await route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers),
                            body=response.content,
                        )

                    await page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                    await page.goto("http://127.0.0.1:8080/code?index=0")
                    await page.evaluate("""clicks => {
                        window.__flagCount = 0;
                        document.addEventListener('htmx:afterRequest', event => {
                            if (event.detail?.requestConfig?.path === '/api/code/flag') {
                                window.__flagCount++;
                            }
                        });
                        for (let i = 0; i < clicks; i++) {
                            document.getElementById('nav-flag-btn').click();
                        }
                        window.aceNavigateNext();
                    }""", flag_clicks)
                    await asyncio.wait_for(flag_started.wait(), timeout=5)
                    if flag_response_first:
                        await asyncio.wait_for(navigation_started.wait(), timeout=5)
                        release_flag.set()
                        await page.wait_for_function("window.__flagCount === 1", timeout=5000)
                        assert "First source text." in await page.locator("#text-panel").inner_text()
                        release_navigation.set()
                    await page.wait_for_function(
                        "window.__aceCurrentIndex === 1 && !document.body.dataset.aceNavigating",
                        timeout=5000,
                    )
                    assert "Second source text." in await page.locator("#text-panel").inner_text()
                    await page.evaluate("window.aceOpenNoteRead(); window.aceEnterEditMode()")
                    await page.locator("#note-textarea").fill("B note pending")
                    release_flag.set()
                    await page.wait_for_function(
                        "clicks => window.__flagCount === clicks",
                        arg=flag_clicks, timeout=5000,
                    )
                    assert "Second source text." in await page.locator("#text-panel").inner_text()
                    assert await page.locator("#nav-flag-btn").get_attribute("aria-pressed") == "false"
                    assert await page.evaluate("""() => {
                        const sources = JSON.parse(document.getElementById('ace-sources-data').textContent);
                        return sources[0].flagged;
                    }""") == bool(flag_clicks % 2)
                    assert ("flagged" in (
                        await page.locator('.ace-grid-tile[data-source-index="0"]').get_attribute("class")
                    ).split()) == bool(flag_clicks % 2)
                    assert await page.locator("#note-textarea").input_value() == "B note pending"
                    await page.wait_for_function(
                        "document.getElementById('note-status')?.textContent.includes('Saved')",
                        timeout=5000,
                    )
                    with sqlite3.connect(project) as stored:
                        assert stored.execute(
                            "SELECT flagged FROM assignment WHERE source_id = ? AND coder_id = ?",
                            (first_id, coder_id),
                        ).fetchone()[0] == flag_clicks % 2
                        assert stored.execute(
                            "SELECT flagged FROM assignment WHERE source_id = ? AND coder_id = ?",
                            (second_id, coder_id),
                        ).fetchone()[0] == 0
                        assert stored.execute(
                            "SELECT note_text FROM source_note WHERE source_id = ? AND coder_id = ?",
                            (second_id, coder_id),
                        ).fetchone()[0] == "B note pending"
                finally:
                    release_flag.set()
                    release_navigation.set()
                    await browser.close()

        asyncio.run(exercise())
