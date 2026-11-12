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
from ace.models.codebook import add_code
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def reorder_server(tmp_path):
    project = tmp_path / "reorder.ace"
    conn = create_project(str(project), "Reorder status")
    # This is ordinary coding text, not an OOB error fragment.
    add_source(conn, "S1", "One sentence. ace-statusbar-event--err", "row")
    first = add_code(conn, "First", "#AA0000")
    second = add_code(conn, "Second", "#00AA00")
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
