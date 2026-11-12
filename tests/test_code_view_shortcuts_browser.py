"""Browser regression for discovering and opening audit shortcuts."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_audit_shortcuts_button_opens_dialog_and_restores_focus(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "audit.ace"
    conn = create_project(str(path), "Audit shortcuts")
    coder_id = list_coders(conn)[0]["id"]
    source_id = add_source(conn, "S1", "One sentence.", "row")
    code_id = add_code(conn, "Alpha", "#AA0000")
    add_annotation(conn, source_id, coder_id, code_id, 0, 13, "One sentence.")
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
                page.goto(f"{base}/code/{code_id}/view")

                opener = page.get_by_role("button", name="? Shortcuts")
                dialog = page.get_by_role("dialog", name="Coded text shortcuts")
                assert opener.is_visible()
                assert not dialog.is_visible()
                opener.focus()
                page.keyboard.press("Enter")
                assert dialog.is_visible()
                page.get_by_role("button", name="Close").click()
                assert not dialog.is_visible()
                assert opener.evaluate("el => document.activeElement === el")

                page.keyboard.press("?")
                assert dialog.is_visible()
                page.keyboard.press("Escape")
                assert not dialog.is_visible()
                assert opener.evaluate("el => document.activeElement === el")

                print_button = page.get_by_role("button", name="Print excerpts")
                assert print_button.is_visible()
                page.evaluate("window.__printCalled = false; window.print = () => { window.__printCalled = true; }")
                print_button.click()
                assert page.evaluate("window.__printCalled")
                page.emulate_media(media="print")
                assert not page.locator("#code-sidebar").is_visible()
                assert page.locator("#cv-table").is_visible()
                assert page.locator("#cv-table").evaluate(
                    "el => getComputedStyle(el).overflowY"
                ) == "visible"
                assert page.locator(".cv-row").count() == 1
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
