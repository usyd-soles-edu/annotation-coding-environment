"""Codebook reorder feedback follows the server's result."""

import asyncio
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def reorder_server(tmp_path):
    project = tmp_path / "reorder.ace"
    conn = create_project(str(project), "Reorder status")
    # This is ordinary coding text, not an OOB error fragment.
    source_one = add_source(conn, "S1", "One sentence. ace-statusbar-event--err", "row")
    add_source(conn, "S2", "Another sentence.", "row")
    first = add_code(conn, "First", "#AA0000")
    second = add_code(conn, "Second", "#00AA00")
    add_annotation(conn, source_one, list_coders(conn)[0]["id"], first, 0, 3, "One")
    conn.close()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for key in ("ACE_LAUNCHER_TOKEN", "ACE_RUNTIME_FILE", "ACE_IDLE_TIMEOUT_SECONDS"):
        env.pop(key, None)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ace.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 8
        while True:
            try:
                with urlopen(base + "/", timeout=0.5):
                    break
            except OSError:
                if server.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("ACE test server did not start")
                time.sleep(0.05)
        yield base, project, first, second
    finally:
        server.terminate()
        server.wait(timeout=5)


def _stored_order(project):
    with sqlite3.connect(project) as stored:
        return [row[0] for row in stored.execute(
            "SELECT id FROM codebook_code WHERE kind = 'code' ORDER BY sort_order"
        )]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_reorder_reports_saved_only_after_success(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, first, second = reorder_server
    with sync_api.sync_playwright() as playwright:
        try:
            browser = getattr(playwright, engine).launch()
        except sync_api.Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip(f"Playwright {engine} is not installed")
            raise
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            first_row = page.locator(f'.ace-ht-row[data-code-id="{first}"]')
            first_row.click()
            page.keyboard.press("Alt+Shift+ArrowDown")
            page.wait_for_function(
                "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
            )
            assert page.locator("[data-headless-tree-status]").text_content() == ""
            assert _stored_order(project) == [second, first]
            page.wait_for_function(
                "document.querySelector('.ace-statusbar-event')?.textContent === ''"
            )

            page.route(
                "**/api/codes/reorder-in-scope",
                lambda route: route.fulfill(status=500, body="save failed"),
            )
            first_row.click()
            with page.expect_response(
                lambda response: response.url.endswith("/api/codes/reorder-in-scope")
                and response.status == 500
            ):
                page.keyboard.press("Alt+Shift+ArrowUp")
            page.wait_for_function(
                "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'"
            )
            assert page.locator(".ace-statusbar-event").text_content() != "Saved"
            assert _stored_order(project) == [second, first]
            assert page.locator("#ace-headless-tree-mount .ace-ht-row[data-code-id]").evaluate_all(
                "rows => rows.map(row => row.dataset.codeId)"
            ) == [str(second), str(first)]
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_reorder_waits_for_pending_server_response(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        request_started = asyncio.Event()
        release_response = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            try:
                browser = await getattr(playwright, engine).launch()
            except async_api.Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip(f"Playwright {engine} is not installed")
                raise
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def hold_reorder(route):
                    request_started.set()
                    await release_response.wait()
                    response = await route.fetch()
                    await route.fulfill(response=response)

                await page.route("**/api/codes/reorder-in-scope", hold_reorder)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(request_started.wait(), timeout=5)
                assert await page.locator(".ace-statusbar-event").text_content() != "Saved"
                assert await page.locator("[data-headless-tree-status]").text_content() == "Saving"
                assert _stored_order(project) == [first, second]
                await page.locator(".ace-sentence").first.click(timeout=2000)
                release_response.set()
                await page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
                )
                assert _stored_order(project) == [second, first]
            finally:
                release_response.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_failed_queued_reorder_restores_last_saved_order(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        both_responses = asyncio.Event()
        responses = []
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                def track_response(response):
                    if response.url.endswith("/api/codes/reorder-in-scope"):
                        responses.append(response.status)
                        if len(responses) == 2:
                            both_responses.set()

                page.on("response", track_response)
                calls = 0

                async def first_succeeds_second_fails(route):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        first_started.set()
                        await release_first.wait()
                        await route.fulfill(response=await route.fetch())
                    else:
                        await route.fulfill(status=500, body="save failed")

                await page.route("**/api/codes/reorder-in-scope", first_succeeds_second_fails)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(first_started.wait(), timeout=5)
                await page.keyboard.press("Alt+Shift+ArrowUp")
                release_first.set()
                await asyncio.wait_for(both_responses.wait(), timeout=8)
                await page.wait_for_load_state("networkidle", timeout=10000)
                diagnostic = await page.evaluate("""() => ({
                    status: document.querySelector('[data-headless-tree-status]')?.textContent,
                    order: [...document.querySelectorAll('#ace-headless-tree-mount .ace-ht-row[data-code-id]')]
                      .map(row => row.dataset.codeId),
                    error: window.__aceHeadlessTreePreviewError,
                })""")
                assert diagnostic["status"] == "Move failed", diagnostic
                assert diagnostic["order"] == [second, first], diagnostic
                assert _stored_order(project) == [second, first]
                assert responses == [200, 500]
            finally:
                release_first.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_three_rapid_reorders_all_settle(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        all_responses = asyncio.Event()
        responses = []
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                def track_response(response):
                    if response.url.endswith("/api/codes/reorder-in-scope"):
                        responses.append(response.status)
                        if len(responses) == 3:
                            all_responses.set()

                page.on("response", track_response)
                calls = 0

                async def hold_first(route):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        first_started.set()
                        await release_first.wait()
                    await route.fulfill(response=await route.fetch())

                await page.route("**/api/codes/reorder-in-scope", hold_first)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(first_started.wait(), timeout=5)
                await page.keyboard.press("Alt+Shift+ArrowUp")
                await page.keyboard.press("Alt+Shift+ArrowDown")
                release_first.set()
                await asyncio.wait_for(all_responses.wait(), timeout=8)
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === ''"
                )
                assert responses == [200, 200, 200]
                assert _stored_order(project) == [second, first]
            finally:
                release_first.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_queued_reorder_waits_for_source_navigation(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        both_responses = asyncio.Event()
        responses = []
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                def track_response(response):
                    if response.url.endswith("/api/codes/reorder-in-scope"):
                        responses.append(response.status)
                        if len(responses) == 2:
                            both_responses.set()

                page.on("response", track_response)
                calls = 0

                async def hold_first(route):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        first_started.set()
                        await release_first.wait()
                    await route.fulfill(response=await route.fetch())

                await page.route("**/api/codes/reorder-in-scope", hold_first)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(first_started.wait(), timeout=5)
                await page.keyboard.press("Alt+Shift+ArrowUp")
                await page.evaluate("window.aceNavigate(1)")
                await page.wait_for_function("document.body.dataset.aceNavigating === '1'")
                release_first.set()
                await asyncio.wait_for(both_responses.wait(), timeout=8)
                await page.wait_for_function(
                    "window.__aceCurrentIndex === 1 && "
                    "document.querySelector('[data-headless-tree-status]')?.textContent === ''"
                )
                assert responses == [200, 200]
                assert _stored_order(project) == [first, second]
            finally:
                release_first.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_reorder_survives_other_htmx_actions(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        first_action_started = asyncio.Event()
        release_first_action = asyncio.Event()
        reorder_response = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def hold_other_action(route):
                    first_action_started.set()
                    await release_first_action.wait()
                    await route.fulfill(status=204)

                await page.route("**/api/code/apply-sentence", hold_other_action)
                page.on("response", lambda response: reorder_response.set()
                        if response.url.endswith("/api/codes/reorder-in-scope") else None)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.evaluate("""() => {
                    void htmx.ajax('POST', '/api/code/apply-sentence', {
                        target: '#text-panel', values: {}
                    });
                }""")
                await asyncio.wait_for(first_action_started.wait(), timeout=5)

                await page.keyboard.press("Alt+Shift+ArrowDown")
                await page.evaluate("""() => {
                    void htmx.ajax('POST', '/api/code/apply-sentence', {
                        target: '#text-panel', values: {}
                    });
                }""")
                # The reorder must complete while the unrelated request is held.
                await asyncio.wait_for(reorder_response.wait(), timeout=5)
                release_first_action.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === ''"
                )
                assert _stored_order(project) == [second, first]
            finally:
                release_first_action.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_delayed_reorder_response_preserves_new_source_details(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        reorder_saved = asyncio.Event()
        release_reorder = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def hold_response(route):
                    response = await route.fetch()
                    reorder_saved.set()
                    await release_reorder.wait()
                    await route.fulfill(response=response)

                await page.route("**/api/codes/reorder-in-scope", hold_response)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(reorder_saved.wait(), timeout=5)
                assert _stored_order(project) == [second, first]
                await page.evaluate("window.aceNavigate(1)")
                await page.wait_for_function(
                    "window.__aceCurrentIndex === 1 && document.body.dataset.aceNavigating !== '1'"
                )
                before = await page.evaluate("""() => ({
                    annotations: document.querySelector('#ace-ann-data')?.outerHTML,
                    inspector: document.querySelector('#ace-right-inspector')?.outerHTML,
                })""")
                assert 'data-annotations="[]"' in before["annotations"]
                assert 'aria-label="0 applied codes"' in before["inspector"]
                release_reorder.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === ''"
                )
                after = await page.evaluate("""() => ({
                    annotations: document.querySelector('#ace-ann-data')?.outerHTML,
                    inspector: document.querySelector('#ace-right-inspector')?.outerHTML,
                })""")
                assert after == before
            finally:
                release_reorder.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
def test_reorder_reconciles_after_sidebar_rebuild(reorder_server):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        reorder_started = asyncio.Event()
        release_reorder = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def hold_reorder(route):
                    reorder_started.set()
                    await release_reorder.wait()
                    await route.fulfill(response=await route.fetch())

                await page.route("**/api/codes/reorder-in-scope", hold_reorder)
                first_row = page.locator(f'.ace-ht-row[data-code-id="{first}"]')
                await first_row.click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(reorder_started.wait(), timeout=5)

                await page.keyboard.press("F2")
                rename_input = page.locator(f'.ace-ht-row[data-code-id="{first}"] input.ace-ht-rename')
                await rename_input.fill("Renamed")
                async with page.expect_response(f"**/api/codes/{first}"):
                    await rename_input.press("Enter")
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').get_by_text("Renamed").wait_for()
                assert _stored_order(project) == [first, second]
                release_reorder.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === ''"
                )
                assert _stored_order(project) == [second, first]
                assert await page.locator(
                    "#ace-headless-tree-mount .ace-ht-row[data-code-id]"
                ).evaluate_all("rows => rows.map(row => row.dataset.codeId)") == [str(second), str(first)]
            finally:
                release_reorder.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_reorder_refreshes_shortcuts_across_single_key_limit(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, _first, _second = reorder_server
    setup = sqlite3.connect(project)
    try:
        setup.row_factory = sqlite3.Row
        for index in range(30):
            add_code(setup, f"Extra {index:02d}", "#123456")
    finally:
        setup.close()
    order = _stored_order(project)
    last_single, first_chord = order[30:32]

    with sync_api.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            single_row = page.locator(f'.ace-ht-row[data-code-id="{last_single}"]')
            chord_row = page.locator(f'.ace-ht-row[data-code-id="{first_chord}"]')
            assert single_row.get_attribute("data-chord") is None
            assert chord_row.get_attribute("data-chord")
            single_row.click()
            with page.expect_response("**/api/codes/reorder-in-scope"):
                page.keyboard.press("Alt+Shift+ArrowDown")
            page.wait_for_function(
                "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
            )
            page.wait_for_function(
                "([single, chord]) => !!document.querySelector(`[data-code-id=\"${single}\"]`)?.dataset.chord "
                "&& !document.querySelector(`[data-code-id=\"${chord}\"]`)?.dataset.chord",
                arg=[last_single, first_chord], timeout=3000,
            )
            assert chord_row.locator(".ace-ht-chip").text_content().strip()
            assert _stored_order(project)[30:32] == [first_chord, last_single]
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_shortcut_refresh_preserves_rename_draft(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, _second = reorder_server

    async def exercise():
        refresh_started = asyncio.Event()
        release_refresh = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').wait_for()

                async def hold_refresh(route):
                    response = await route.fetch()
                    refresh_started.set()
                    await release_refresh.wait()
                    await route.fulfill(response=response)

                await page.route("**/api/codes/tree", hold_refresh)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(refresh_started.wait(), timeout=5)
                await page.keyboard.press("F2")
                rename_input = page.locator(f'.ace-ht-row[data-code-id="{first}"] input.ace-ht-rename')
                await rename_input.fill("Unsaved draft")
                release_refresh.set()
                await page.wait_for_load_state("networkidle", timeout=5000)
                assert await rename_input.input_value(timeout=2000) == "Unsaved draft"
                assert await rename_input.evaluate("el => document.activeElement === el")
            finally:
                release_refresh.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_undo_invalidates_delayed_shortcut_refresh(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, _first, _second = reorder_server
    setup = sqlite3.connect(project)
    try:
        setup.row_factory = sqlite3.Row
        for index in range(30):
            add_code(setup, f"Extra {index:02d}", "#123456")
    finally:
        setup.close()
    original = _stored_order(project)
    last_single, first_chord = original[30:32]

    async def exercise():
        refresh_started = asyncio.Event()
        release_refresh = asyncio.Event()
        refresh_calls = 0
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")
                await page.locator(f'.ace-ht-row[data-code-id="{last_single}"]').wait_for()

                async def hold_refresh(route):
                    nonlocal refresh_calls
                    refresh_calls += 1
                    if refresh_calls > 1:
                        await route.continue_()
                        return
                    response = await route.fetch()
                    refresh_started.set()
                    await release_refresh.wait()
                    await route.fulfill(response=response)

                await page.route("**/api/codes/tree", hold_refresh)
                await page.locator(f'.ace-ht-row[data-code-id="{last_single}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(refresh_started.wait(), timeout=5)
                await page.locator(".ace-sentence").first.click()
                async with page.expect_response("**/api/undo"):
                    await page.keyboard.press("z")
                await page.wait_for_function(
                    "([single, chord]) => !document.querySelector(`[data-code-id=\"${single}\"]`)?.dataset.chord "
                    "&& !!document.querySelector(`[data-code-id=\"${chord}\"]`)?.dataset.chord",
                    arg=[last_single, first_chord], timeout=5000,
                )
                assert _stored_order(project) == original
                release_refresh.set()
                await page.wait_for_load_state("networkidle", timeout=5000)
                assert await page.locator(
                    f'.ace-ht-row[data-code-id="{last_single}"]'
                ).get_attribute("data-chord") is None
                assert await page.locator(
                    f'.ace-ht-row[data-code-id="{first_chord}"]'
                ).get_attribute("data-chord")
            finally:
                release_refresh.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_undo_wins_over_delayed_reorder_response(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        reorder_saved = asyncio.Event()
        release_reorder = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def hold_response(route):
                    response = await route.fetch()
                    reorder_saved.set()
                    await release_reorder.wait()
                    await route.fulfill(response=response)

                await page.route("**/api/codes/reorder-in-scope", hold_response)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(reorder_saved.wait(), timeout=5)
                assert _stored_order(project) == [second, first]
                await page.locator(".ace-sentence").first.click()
                async with page.expect_response("**/api/undo"):
                    await page.keyboard.press("z")
                await page.wait_for_function(
                    "([first, second]) => [...document.querySelectorAll("
                    "'#ace-headless-tree-mount .ace-ht-row[data-code-id]')]"
                    ".map(row => row.dataset.codeId).join(',') === [first, second].join(',')",
                    arg=[first, second], timeout=5000,
                )
                assert _stored_order(project) == [first, second]
                release_reorder.set()
                await page.wait_for_load_state("networkidle", timeout=5000)
                assert await page.locator(
                    "#ace-headless-tree-mount .ace-ht-row[data-code-id]"
                ).evaluate_all("rows => rows.map(row => row.dataset.codeId)") == [str(first), str(second)]
            finally:
                release_reorder.set()
                await browser.close()

    asyncio.run(exercise())

@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_failed_keyboard_drag_restores_saved_order(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, first, second = reorder_server
    with sync_api.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            page.route(
                "**/api/codes/reorder-in-scope",
                lambda route: route.fulfill(status=500, body="save failed"),
            )
            page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
            page.keyboard.press("Control+Shift+d")
            assert "Moving" in page.locator("#ace-headless-tree-dnd-live").text_content()
            page.keyboard.press("ArrowDown")
            with page.expect_response(
                lambda response: response.url.endswith("/api/codes/reorder-in-scope")
                and response.status == 500,
                timeout=5000,
            ):
                page.keyboard.press("Enter")
            page.wait_for_function(
                "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'",
                timeout=2000,
            )
            assert page.locator("#ace-headless-tree-mount .ace-ht-row[data-code-id]").evaluate_all(
                "rows => rows.map(row => row.dataset.codeId)"
            ) == [str(first), str(second)]
            assert _stored_order(project) == [first, second]
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_keyboard_drag_enter_completes_move(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, first, second = reorder_server
    with sync_api.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
            with sqlite3.connect(project) as stored:
                annotations_before_drag = stored.execute(
                    "SELECT COUNT(*) FROM annotation"
                ).fetchone()[0]
            page.keyboard.press("Control+Shift+d")
            assert "Moving" in page.locator("#ace-headless-tree-dnd-live").text_content()
            page.keyboard.press("ArrowDown")
            with page.expect_response("**/api/codes/reorder-in-scope", timeout=5000):
                page.keyboard.press("Enter")
            page.wait_for_function(
                "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
            )
            assert _stored_order(project) == [second, first]
            with sqlite3.connect(project) as stored:
                assert stored.execute(
                    "SELECT COUNT(*) FROM annotation"
                ).fetchone()[0] == annotations_before_drag
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_failed_reparent_drag_restores_saved_parent(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, first, _second = reorder_server
    with sqlite3.connect(project) as setup:
        setup.row_factory = sqlite3.Row
        folder = add_folder(setup, "Group")
    with sync_api.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            page.route(
                f"**/api/codes/{first}/parent",
                lambda route: route.fulfill(status=500, body="save failed"),
            )
            source_row = page.locator(f'.ace-ht-row[data-code-id="{first}"]')
            folder_row = page.locator(f'.ace-ht-row[data-folder-id="{folder}"]')
            with page.expect_response(f"**/api/codes/{first}/parent", timeout=5000):
                source_row.drag_to(folder_row)
            page.wait_for_function(
                "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'",
                timeout=2000,
            )
            with sqlite3.connect(project) as stored:
                assert stored.execute(
                    "SELECT parent_id FROM codebook_code WHERE id = ?", (first,)
                ).fetchone()[0] is None
            assert source_row.get_attribute("aria-level") == "1"
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_reparent_drag_saves_new_folder(reorder_server, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, project, first, _second = reorder_server
    with sqlite3.connect(project) as setup:
        setup.row_factory = sqlite3.Row
        folder = add_folder(setup, "Group")
    with sync_api.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        try:
            page = browser.new_page()
            page.goto(base + "/")
            assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
            page.goto(base + "/code")
            source_row = page.locator(f'.ace-ht-row[data-code-id="{first}"]')
            folder_row = page.locator(f'.ace-ht-row[data-folder-id="{folder}"]')
            with page.expect_response(f"**/api/codes/{first}/parent", timeout=5000):
                source_row.drag_to(folder_row)
            page.wait_for_function(
                "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
            )
            with sqlite3.connect(project) as stored:
                assert stored.execute(
                    "SELECT parent_id FROM codebook_code WHERE id = ?", (first,)
                ).fetchone()[0] == folder
            assert source_row.get_attribute("aria-level") == "2"
        finally:
            browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_failed_drag_cannot_erase_newer_sidebar(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, _second = reorder_server

    async def exercise():
        reorder_sent = asyncio.Event()
        release_failure = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def delay_failed_save(route):
                    reorder_sent.set()
                    await release_failure.wait()
                    await route.fulfill(status=500, body="save failed")

                await page.route("**/api/codes/reorder-in-scope", delay_failed_save)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Control+Shift+d")
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                await asyncio.wait_for(reorder_sent.wait(), timeout=5)
                async with page.expect_response("**/api/codes/folder"):
                    await page.evaluate("""() => window.htmx.ajax('POST', '/api/codes/folder', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {name: 'Newer folder', current_index: 0}
                    })""")
                await page.locator('.ace-ht-row[data-kind="folder"]').wait_for()
                release_failure.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'"
                )
                assert await page.locator('.ace-ht-row[data-kind="folder"]').count() == 1
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT COUNT(*) FROM codebook_code WHERE kind = 'folder'"
                    ).fetchone()[0] == 1
            finally:
                release_failure.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_second_drag_waits_for_failed_save(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        first_sent = asyncio.Event()
        release_failure = asyncio.Event()
        request_count = 0
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def fail_saves(route):
                    nonlocal request_count
                    request_count += 1
                    first_sent.set()
                    await release_failure.wait()
                    await route.fulfill(status=500, body="save failed")

                await page.route("**/api/codes/reorder-in-scope", fail_saves)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Control+Shift+d")
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                await asyncio.wait_for(first_sent.wait(), timeout=5)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Control+Shift+d")
                assert await page.evaluate(
                    "() => !window.__aceHeadlessTreePreview.tree.getState().dnd"
                )
                assert request_count == 1
                release_failure.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'"
                )
                await page.wait_for_load_state("networkidle")
                assert request_count == 1
                assert await page.locator(
                    "#ace-headless-tree-mount .ace-ht-row[data-code-id]"
                ).evaluate_all("rows => rows.map(row => row.dataset.codeId)") == [str(first), str(second)]
                assert _stored_order(project) == [first, second]
            finally:
                release_failure.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_keyboard_reorder_waits_for_drag_save(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        drag_sent = asyncio.Event()
        release_failure = asyncio.Event()
        requests = 0
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def fail_drag(route):
                    nonlocal requests
                    requests += 1
                    drag_sent.set()
                    await release_failure.wait()
                    await route.fulfill(status=500, body="save failed")

                await page.route("**/api/codes/reorder-in-scope", fail_drag)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Control+Shift+d")
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                await asyncio.wait_for(drag_sent.wait(), timeout=5)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowUp")
                assert await page.locator(
                    "#ace-headless-tree-mount .ace-ht-row[data-code-id]"
                ).evaluate_all("rows => rows.map(row => row.dataset.codeId)") == [str(second), str(first)]
                release_failure.set()
                await page.wait_for_function(
                    "document.querySelector('[data-headless-tree-status]')?.textContent === 'Move failed'"
                )
                await page.wait_for_load_state("networkidle")
                assert requests == 1
                assert _stored_order(project) == [first, second]
                assert await page.locator(
                    "#ace-headless-tree-mount .ace-ht-row[data-code-id]"
                ).evaluate_all("rows => rows.map(row => row.dataset.codeId)") == [str(first), str(second)]
            finally:
                release_failure.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_drag_waits_for_keyboard_reorder_save(reorder_server, engine):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, second = reorder_server

    async def exercise():
        reorder_sent = asyncio.Event()
        release_success = asyncio.Event()
        requests = 0
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")

                async def delay_keyboard_reorder(route):
                    nonlocal requests
                    requests += 1
                    reorder_sent.set()
                    await release_success.wait()
                    await route.fulfill(response=await route.fetch())

                await page.route("**/api/codes/reorder-in-scope", delay_keyboard_reorder)
                await page.locator(f'.ace-ht-row[data-code-id="{first}"]').click()
                await page.keyboard.press("Alt+Shift+ArrowDown")
                await asyncio.wait_for(reorder_sent.wait(), timeout=5)
                await page.keyboard.press("Control+Shift+d")
                assert await page.evaluate(
                    "() => !window.__aceHeadlessTreePreview.tree.getState().dnd"
                )
                release_success.set()
                await page.wait_for_load_state("networkidle")
                assert requests == 1
                assert _stored_order(project) == [second, first]
            finally:
                release_success.set()
                await browser.close()

    asyncio.run(exercise())


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("move_kind", ["reorder", "reparent"])
def test_delayed_drag_save_preserves_destination_source(reorder_server, engine, move_kind):
    async_api = pytest.importorskip("playwright.async_api")
    base, project, first, _second = reorder_server
    if move_kind == "reparent":
        with sqlite3.connect(project) as setup:
            setup.row_factory = sqlite3.Row
            folder = add_folder(setup, "Group")

    async def exercise():
        drag_saved = asyncio.Event()
        release_response = asyncio.Event()
        async with async_api.async_playwright() as playwright:
            browser = await getattr(playwright, engine).launch()
            try:
                page = await browser.new_page()
                await page.goto(base + "/")
                assert (await page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                )).ok
                await page.goto(base + "/code")
                first_annotations = await page.locator("#ace-ann-data").get_attribute(
                    "data-annotations"
                )

                async def hold_drag_response(route):
                    response = await route.fetch()
                    drag_saved.set()
                    await release_response.wait()
                    await route.fulfill(response=response)

                route_pattern = (
                    "**/api/codes/reorder-in-scope" if move_kind == "reorder"
                    else f"**/api/codes/{first}/parent"
                )
                await page.route(route_pattern, hold_drag_response)
                source_row = page.locator(f'.ace-ht-row[data-code-id="{first}"]')
                if move_kind == "reorder":
                    await source_row.click()
                    await page.keyboard.press("Control+Shift+d")
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                else:
                    await source_row.drag_to(
                        page.locator(f'.ace-ht-row[data-folder-id="{folder}"]')
                    )
                await asyncio.wait_for(drag_saved.wait(), timeout=5)
                async with page.expect_response("**/api/navigation"):
                    await page.evaluate("window.aceNavigate(1)")
                await page.wait_for_function("window.__aceCurrentIndex === 1")
                destination_annotations = await page.locator(
                    "#ace-ann-data"
                ).get_attribute("data-annotations")
                assert destination_annotations != first_annotations
                release_response.set()
                await page.wait_for_load_state("networkidle", timeout=5000)
                assert await page.locator("#ace-ann-data").get_attribute(
                    "data-annotations"
                ) == destination_annotations
                assert await page.evaluate("window.__aceCurrentIndex") == 1
            finally:
                release_response.set()
                await browser.close()

    asyncio.run(exercise())
