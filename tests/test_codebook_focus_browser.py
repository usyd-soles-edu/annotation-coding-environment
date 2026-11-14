"""Focus-only codebook navigation keeps rows mounted and accessible."""

import os
import sqlite3
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
                assert alpha.get_attribute("aria-keyshortcuts") == "1 Shift+F10 ContextMenu"
                assert beta.get_attribute("aria-keyshortcuts") == "2 Shift+F10 ContextMenu"

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

                beta.focus()
                page.keyboard.press("Control+Home")
                assert beta.get_attribute("tabindex") == "0"
                page.keyboard.press("Control+ArrowRight")
                assert page.evaluate(
                    "document.getElementById('ace-headless-tree-mount').contains(document.activeElement)"
                )

                def wait_focused(item_id):
                    page.wait_for_function(
                        "id => document.querySelector(`.ace-ht-row[data-item-id='${id}']`)?.tabIndex === 0",
                        arg=str(item_id),
                        timeout=2000,
                    )

                page.keyboard.press("Home")
                wait_focused(first_folder)
                page.keyboard.press("End")
                wait_focused(second_code)
                page.keyboard.press("ArrowUp")
                wait_focused(second_folder)
                page.keyboard.press("ArrowDown")
                wait_focused(second_code)
                page.keyboard.press("ArrowRight")
                page.wait_for_function(
                    "!document.getElementById('ace-headless-tree-mount').contains(document.activeElement)",
                    timeout=2000,
                )
                focus(second_folder)
                folder_b.focus()
                source_focus = page.evaluate("""() => {
                    const press = key => {
                        const target = document.activeElement;
                        target.dispatchEvent(new KeyboardEvent('keydown', {
                            key, bubbles: true, cancelable: true,
                        }));
                        target.dispatchEvent(new KeyboardEvent('keyup', {key, bubbles: true}));
                    };
                    press('ArrowDown');
                    press('ArrowRight');
                    return {
                        activeId: document.activeElement?.id,
                        focusedItemId: window.__aceHeadlessTreePreview.tree.getFocusedItem()?.getId(),
                    };
                }""")
                assert source_focus == {
                    "activeId": "text-panel",
                    "focusedItemId": str(second_code),
                }
                page.wait_for_timeout(100)
                assert page.evaluate("document.activeElement?.id") == "text-panel"
                focus(first_folder)
                folder_a.focus()
                page.evaluate("""() => {
                    const mount = document.getElementById('ace-headless-tree-mount');
                    mount.style.cssText = 'height: 48px; flex: 0 0 48px; overflow: auto';
                    mount.scrollTop = 0;
                    mount.addEventListener('keydown', event => {
                        if (event.key === 'End') event.preventDefault();
                    }, {capture: true, once: true});
                }""")
                page.keyboard.press("End")
                wait_focused(second_code)
                assert page.evaluate(
                    "document.getElementById('ace-headless-tree-mount').scrollTop"
                ) > 0
                page.evaluate("document.getElementById('ace-headless-tree-mount').removeAttribute('style')")
                focus(second_code)
                beta.focus()

                search = page.locator("#code-search-input")
                search.focus()
                page.keyboard.press("Tab")
                assert page.evaluate("document.activeElement?.dataset.itemId") == str(second_code)
                page.keyboard.press("Shift+Tab")
                assert page.evaluate("document.activeElement?.id") == "code-search-input"
                page.locator("#text-panel").focus()
                page.keyboard.press("Shift+Tab")
                assert page.evaluate("document.activeElement?.dataset.itemId") == str(second_code)

                search.fill("Beta")
                page.wait_for_function(
                    "id => !document.querySelector(`.ace-ht-row[data-code-id='${id}']`)",
                    arg=str(first_code),
                    timeout=2000,
                )
                assert alpha.count() == 0
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-code-id='${id}'] .ace-ht-chip`)?.textContent === '1'",
                    arg=str(second_code),
                    timeout=2000,
                )
                assert beta.locator(".ace-ht-chip").get_attribute("title") == "Press 1 or Enter to apply Beta"
                assert beta.get_attribute("aria-keyshortcuts") == "1 Shift+F10 ContextMenu"
                search.fill("")
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-code-id='${id}'] .ace-ht-chip`)?.textContent === '2'",
                    arg=str(second_code),
                    timeout=2000,
                )
                assert beta.get_attribute("aria-keyshortcuts") == "2 Shift+F10 ContextMenu"
                folder_a.locator(".ace-ht-toggle").click()
                assert folder_a.get_attribute("aria-expanded") == "false"
                assert alpha.count() == 0
                assert beta.locator(".ace-ht-chip").text_content() == "1"
                assert beta.get_attribute("aria-keyshortcuts") == "1 Shift+F10 ContextMenu"

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
                page.locator(".ace-sentence").first.click()
                page.keyboard.press("1")
                page.wait_for_function(
                    "document.querySelectorAll('.ace-applied-code-row').length === 1"
                )
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT code_id FROM annotation WHERE deleted_at IS NULL"
                    ).fetchone()[0] == second_code

                page.goto(f"{base}/code/{second_code}/view")
                audit_beta = page.locator(f'.ace-ht-row[data-code-id="{second_code}"]')
                audit_beta.wait_for()
                assert audit_beta.locator(".ace-ht-chip").text_content() == ""
                assert audit_beta.get_attribute("aria-keyshortcuts") == "Shift+F10 ContextMenu"
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
