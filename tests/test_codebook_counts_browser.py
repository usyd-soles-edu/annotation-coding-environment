"""Browser regression for code counts surviving headless-tree rerenders."""

import os
import socket
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

                focus_without_rerender(beta.click)
                assert count_state() == {"shown": "1", "cached": 1}
                search = page.locator("#code-search-input")
                rerender_after(lambda: search.fill("Alpha"))
                assert count_state() == {"shown": "1", "cached": 1}
                rerender_after(lambda: search.fill(""))

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
