"""Cut state survives tree renders and rejected pastes."""

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
def test_cut_ghost_survives_code_and_folder_focus_changes(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "cut.ace"
    conn = create_project(str(project), "Cut test")
    add_source(conn, "S1", "One. Two.", "row")
    add_code(conn, "Alpha", "#FF0000")
    add_code(conn, "Beta", "#00FF00")
    add_folder(conn, "Group")
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
                opened = page.request.post(base + "/api/project/open", form={"path": str(project)})
                assert opened.ok
                page.goto(base + "/code")
                codes = page.locator('.ace-ht-row[data-kind="code"]')
                codes.first.click()
                cut_id = codes.first.get_attribute("data-item-id")
                page.keyboard.press("Meta+x")
                assert page.evaluate(
                    "window.AceHeadlessTreePreview.getController().getCutItemId()"
                ) == cut_id
                cut_row = page.locator(f'.ace-ht-row[data-item-id="{cut_id}"]')
                page.evaluate("""() => htmx.ajax('POST', '/api/codes/reorder', {
                    target: '#code-sidebar', swap: 'outerHTML',
                    values: { code_ids: '[]', current_index: 0 },
                })""")
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-item-id='${id}']`)?.classList.contains('ace-code-row--ghost')",
                    arg=cut_id,
                )
                assert page.evaluate(
                    "window.AceHeadlessTreePreview.getController().getCutItemId()"
                ) == cut_id
                codes.nth(1).click()
                assert "ace-code-row--ghost" in cut_row.get_attribute("class")
                assert cut_row.evaluate("el => getComputedStyle(el).opacity") == "0.4"

                # The target can disappear in another tab while its row is
                # still visible here. A rejected paste must keep the cut item.
                target_id = codes.nth(1).get_attribute("data-item-id")
                db = sqlite3.connect(project)
                try:
                    db.execute(
                        "UPDATE codebook_code SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (target_id,),
                    )
                    db.commit()
                finally:
                    db.close()
                page.keyboard.press("Meta+v")
                page.wait_for_function("""() =>
                    document.getElementById('ace-statusbar-event')?.textContent.includes('target_id not found')
                """)
                assert page.evaluate(
                    "window.AceHeadlessTreePreview.getController().getCutItemId()"
                ) == cut_id
                assert "ace-code-row--ghost" in cut_row.get_attribute("class")
                db = sqlite3.connect(project)
                try:
                    db.execute(
                        "UPDATE codebook_code SET deleted_at = NULL WHERE id = ?",
                        (target_id,),
                    )
                    db.commit()
                finally:
                    db.close()

                page.keyboard.press("Escape")
                assert page.evaluate(
                    "window.AceHeadlessTreePreview.getController().getCutItemId()"
                ) is None
                assert "ace-code-row--ghost" not in cut_row.get_attribute("class")
                cut_row.click()
                page.keyboard.press("Meta+x")
                folder = page.locator('.ace-ht-row[data-kind="folder"]').first
                folder_id = folder.get_attribute("data-item-id")
                folder.click()
                page.keyboard.press("Meta+v")
                page.wait_for_function("""() =>
                    window.AceHeadlessTreePreview.getController().getCutItemId() === null
                """)
                db = sqlite3.connect(project)
                try:
                    assert db.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (cut_id,)
                    ).fetchone()[0] == folder_id
                finally:
                    db.close()

                # The empty-area menu uses an empty target ID to paste at root.
                cut_row.click()
                page.keyboard.press("Meta+x")
                page.locator("#ace-headless-tree-mount").evaluate("""el =>
                    el.dispatchEvent(new MouseEvent('contextmenu', {
                        bubbles: true, button: 2, clientX: 12, clientY: 12
                    }))
                """)
                page.get_by_role("menu", name="Codebook actions").get_by_role(
                    "menuitem", name="Paste here"
                ).click()
                page.wait_for_function("""() =>
                    window.AceHeadlessTreePreview.getController().getCutItemId() === null
                """)
                db = sqlite3.connect(project)
                try:
                    assert db.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (cut_id,)
                    ).fetchone()[0] is None
                finally:
                    db.close()

                # HTMX resolves a queued ajax() promise before it sends the
                # request. The cut state must clear when the actual response
                # arrives, even if another request was already in flight.
                cut_row.click()
                page.keyboard.press("Meta+x")
                folder = page.locator('.ace-ht-row[data-kind="folder"]').first
                folder.click()
                page.evaluate("""() => {
                    const open = XMLHttpRequest.prototype.open;
                    const send = XMLHttpRequest.prototype.send;
                    window.__restoreXHR = () => {
                        XMLHttpRequest.prototype.open = open;
                        XMLHttpRequest.prototype.send = send;
                    };
                    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                        this.__holdCodebookRequest = url.includes('/api/codes/reorder');
                        return open.call(this, method, url, ...rest);
                    };
                    XMLHttpRequest.prototype.send = function(body) {
                        if (this.__holdCodebookRequest) {
                            window.__releaseCodebookRequest = () => send.call(this, body);
                            return;
                        }
                        return send.call(this, body);
                    };
                    window.__pasteRequestsStarted = 0;
                    document.addEventListener('htmx:beforeRequest', event => {
                        if (event.detail?.requestConfig?.path === '/api/codes/cut-paste') {
                            window.__pasteRequestsStarted += 1;
                        }
                    });
                    htmx.ajax('POST', '/api/codes/reorder', {
                        target: '#code-sidebar', swap: 'outerHTML',
                        values: {code_ids: '[]', current_index: 0}
                    });
                }""")
                page.wait_for_function("window.__releaseCodebookRequest !== undefined")
                page.keyboard.press("Meta+v")
                assert page.evaluate("window.__pasteRequestsStarted") == 0
                page.evaluate("window.__releaseCodebookRequest()")
                page.wait_for_function("""() =>
                    window.AceHeadlessTreePreview.getController().getCutItemId() === null
                """, timeout=5000)
                assert page.evaluate("window.__pasteRequestsStarted") == 1
                page.evaluate("window.__restoreXHR()")
                db = sqlite3.connect(project)
                try:
                    assert db.execute(
                        "SELECT parent_id FROM codebook_code WHERE id = ?", (cut_id,)
                    ).fetchone()[0] == folder_id
                finally:
                    db.close()

                folder = page.locator('.ace-ht-row[data-kind="folder"]').first
                folder.click()
                page.keyboard.press("Meta+x")
                assert page.evaluate(
                    "window.AceHeadlessTreePreview.getController().getCutItemId()"
                ) == folder_id
                codes.first.click()
                folder_row = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                assert "ace-code-row--ghost" in folder_row.get_attribute("class")
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
