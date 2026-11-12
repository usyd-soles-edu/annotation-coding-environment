"""Focus-only codebook navigation keeps rows mounted and accessible."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_focus_changes_preserve_rows_and_update_tree_state(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "focus.ace"
    conn = create_project(str(project), "Focus test")
    add_source(conn, "Sample", "One sentence.", "row")
    first_folder = add_folder(conn, "First folder")
    first_code = add_code(conn, "Alpha", "#AA0000", parent_id=first_folder)
    second_folder = add_folder(conn, "Second folder")
    second_code = add_code(conn, "Beta", "#00AA00", parent_id=second_folder)
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
                assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
                page.goto(base + "/code")
                alpha = page.locator(f'.ace-ht-row[data-code-id="{first_code}"]')
                beta = page.locator(f'.ace-ht-row[data-code-id="{second_code}"]')
                folder_a = page.locator(f'.ace-ht-row[data-folder-id="{first_folder}"]')
                folder_b = page.locator(f'.ace-ht-row[data-folder-id="{second_folder}"]')
                alpha.wait_for()
                assert alpha.locator(".ace-ht-chip").text_content() == "1"
                assert beta.locator(".ace-ht-chip").text_content() == "2"

                def focus(item_id):
                    page.evaluate(
                        "id => window.__aceHeadlessTreePreview.tree.getItemInstance(id).setFocused()",
                        str(item_id),
                    )
                    page.wait_for_function(
                        "id => document.querySelector(`.ace-ht-row[data-item-id='${id}']`)?.tabIndex === 0",
                        arg=str(item_id),
                    )

                focus(first_code)
                alpha_element = alpha.element_handle()
                beta_element = beta.element_handle()
                assert "ace-ht-row--path-parent" in folder_a.get_attribute("class")
                focus(second_code)
                assert alpha_element.evaluate("el => el.isConnected")
                assert beta_element.evaluate("el => el.isConnected")
                assert alpha.get_attribute("tabindex") == "-1"
                assert beta.get_attribute("tabindex") == "0"
                assert beta.get_attribute("aria-label") == "Beta"
                assert beta.get_attribute("aria-level") == "2"
                assert "ace-ht-row--path-parent" not in folder_a.get_attribute("class")
                assert "ace-ht-row--path-parent" in folder_b.get_attribute("class")

                search = page.locator("#code-search-input")
                search.fill("Beta")
                assert alpha.count() == 0
                assert beta.locator(".ace-ht-chip").text_content() == "1"
                search.fill("")
                assert beta.locator(".ace-ht-chip").text_content() == "2"
                folder_a.locator(".ace-ht-toggle").click()
                assert folder_a.get_attribute("aria-expanded") == "false"
                assert alpha.count() == 0

                folder_a.focus()
                page.evaluate("document.getElementById('ace-live-region').textContent = ''")
                page.keyboard.press("Alt+Shift+ArrowUp")
                assert page.locator("#ace-live-region").inner_text() == ""
                assert page.evaluate(
                    "window.__aceHeadlessTreePreview.snapshot().rootChildren"
                ) == [first_folder, second_folder]
                page.keyboard.press("Alt+Shift+ArrowDown")
                page.wait_for_function(
                    "ids => JSON.stringify(window.__aceHeadlessTreePreview.snapshot().rootChildren) === JSON.stringify(ids)",
                    arg=[second_folder, first_folder],
                )
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent === 'Saved'"
                )
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
