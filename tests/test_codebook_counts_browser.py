"""Browser regression for code counts surviving headless-tree rerenders."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_annotation_count_survives_focus_search_and_delete(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "counts.ace"
    conn = create_project(str(path), "Tree counts")
    add_source(conn, "S1", "One. Two.", "row")
    add_source(conn, "S2", "Three. Four.", "row")
    alpha_id = add_code(conn, "Alpha", "#AA0000")
    add_code(conn, "Beta", "#00AA00")
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
                assert page.request.post(base + "/api/project/open", form={"path": str(path)}).ok
                page.goto(base + "/code")
                alpha = page.locator(f'.ace-ht-row[data-code-id="{alpha_id}"]')
                beta = page.locator('.ace-ht-row[data-kind="code"]').nth(1)
                alpha.wait_for()

                def count_state():
                    return page.evaluate("""id => ({
                      shown: document.querySelector(`.ace-ht-row[data-code-id="${id}"] .ace-ht-count`)?.textContent,
                      cached: window.__aceHeadlessTreePreview?.items[id]?.count
                    })""", alpha_id)

                def rerender_after(action):
                    old_row = alpha.element_handle()
                    action()
                    page.wait_for_function("row => !row.isConnected", arg=old_row)

                def focus_without_rerender(action):
                    old_row = alpha.element_handle()
                    action()
                    page.wait_for_function("""() =>
                      document.querySelectorAll('.ace-ht-row[data-kind="code"]')[1]?.tabIndex === 0
                    """)
                    assert old_row.evaluate("row => row.isConnected")

                assert count_state() == {"shown": "", "cached": 0}
                page.evaluate("""async id => {
                  await htmx.ajax('POST', '/api/code/apply-sentence', {
                    target: '#text-panel', swap: 'outerHTML',
                    values: {code_id: id, sentence_index: 0, current_index: 0}
                  });
                }""", alpha_id)
                page.wait_for_function("""id =>
                  document.querySelector(`.ace-ht-row[data-code-id="${id}"] .ace-ht-count`)?.textContent === '1'
                """, arg=alpha_id)
                assert count_state() == {"shown": "1", "cached": 1}

                # The next source has no annotation, but the codebook count
                # covers the whole project rather than only the visible text.
                page.evaluate("window.aceNavigate(1)")
                page.wait_for_function("window.__aceCurrentIndex === 1")
                assert count_state() == {"shown": "1", "cached": 1}
                page.evaluate("window.aceNavigate(0)")
                page.wait_for_function("window.__aceCurrentIndex === 0")
                assert count_state() == {"shown": "1", "cached": 1}

                focus_without_rerender(beta.click)
                assert count_state() == {"shown": "1", "cached": 1}
                search = page.locator("#code-search-input")
                rerender_after(lambda: search.fill("Alpha"))
                assert count_state() == {"shown": "1", "cached": 1}
                rerender_after(lambda: search.fill(""))

                # A codebook mutation replaces the sidebar and reloads the
                # tree while the project-wide count snapshot is unchanged.
                page.evaluate("""async () => {
                  await htmx.ajax('POST', '/api/codes', {
                    target: '#code-sidebar', swap: 'outerHTML',
                    values: {name: 'Gamma', current_index: 0}
                  });
                }""")
                page.locator('.ace-ht-row[aria-label="Gamma"]').wait_for()
                assert count_state() == {"shown": "1", "cached": 1}

                annotation_id = page.locator("#ace-ann-data").evaluate(
                    "el => JSON.parse(el.dataset.annotations)[0].id"
                )
                page.evaluate("""async id => {
                  await htmx.ajax('POST', '/api/code/delete-annotation', {
                    target: '#text-panel', swap: 'outerHTML',
                    values: {annotation_id: id, current_index: 0}
                  });
                }""", annotation_id)
                page.wait_for_function("""id =>
                  window.__aceHeadlessTreePreview?.items[id]?.count === 0
                """, arg=alpha_id)
                assert count_state() == {"shown": "", "cached": 0}
                focus_without_rerender(beta.click)
                assert count_state() == {"shown": "", "cached": 0}
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_count_patches_survive_stale_tree_reload(tmp_path, engine):
    async_api = pytest.importorskip("playwright.async_api")
    path = tmp_path / "count-race.ace"
    conn = create_project(str(path), "Count reload")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    alpha_id = add_code(conn, "Alpha", "#AA0000")
    beta_id = add_code(conn, "Beta", "#00AA00")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(path)
        app.state.coder_id = coder_id

        async def exercise():
            hold_tree = False
            stale_tree_ready = asyncio.Event()
            release_tree = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, engine).launch()
                try:
                    page = await browser.new_page()

                    async def serve(route):
                        request = route.request
                        url = urlsplit(request.url)
                        path_with_query = url.path + (f"?{url.query}" if url.query else "")
                        headers = {
                            key: value for key, value in request.headers.items()
                            if key.lower() not in {"host", "content-length"}
                        }
                        response = client.request(
                            request.method, path_with_query,
                            content=request.post_data_buffer, headers=headers,
                        )
                        if hold_tree and url.path == "/api/codes/tree":
                            stale_tree_ready.set()
                            await release_tree.wait()
                        await route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers), body=response.content,
                        )

                    await page.route("http://127.0.0.1:8080/**", serve)
                    await page.goto("http://127.0.0.1:8080/code")
                    await page.locator(f'.ace-ht-row[data-code-id="{alpha_id}"]').wait_for()
                    hold_tree = True
                    mutation = asyncio.create_task(page.evaluate("""() =>
                        htmx.ajax('POST', '/api/codes', {
                            target: '#code-sidebar', swap: 'outerHTML',
                            values: {name: 'Gamma', current_index: 0}
                        })"""))
                    await asyncio.wait_for(stale_tree_ready.wait(), timeout=5)
                    await page.evaluate("""id => htmx.ajax('POST', '/api/code/apply-sentence', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {code_id: id, sentence_index: 0, current_index: 0}
                    })""", alpha_id)
                    await page.wait_for_function("""id =>
                        window.__aceHeadlessTreePreview?.items[id]?.count === 1
                    """, arg=alpha_id)
                    await page.evaluate("""id => htmx.ajax('POST', '/api/code/apply-sentence', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {code_id: id, sentence_index: 0, current_index: 0}
                    })""", beta_id)
                    await page.wait_for_function("""id =>
                        window.__aceHeadlessTreePreview?.items[id]?.count === 1
                    """, arg=beta_id)
                    release_tree.set()
                    await mutation
                    await page.locator('.ace-ht-row[aria-label="Gamma"]').wait_for()
                    for code_id in (alpha_id, beta_id):
                        assert await page.locator(
                            f'.ace-ht-row[data-code-id="{code_id}"] .ace-ht-count'
                        ).inner_text() == "1"
                        assert await page.evaluate("""id =>
                            window.__aceHeadlessTreePreview.items[id].count""", code_id) == 1
                finally:
                    release_tree.set()
                    await browser.close()

        asyncio.run(exercise())
