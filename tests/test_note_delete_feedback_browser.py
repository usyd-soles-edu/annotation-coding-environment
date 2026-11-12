"""Clearing a saved source note reports the deletion after it succeeds."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_clearing_saved_note_reports_deletion(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Note deletion")
    source_id = add_source(conn, "S1", "One sentence.", "row")
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
                page.locator("#note-pill").click()
                page.locator("#note-pill").click()
                page.locator("#note-textarea").fill("A saved note")
                page.wait_for_function(
                    "document.querySelector('#note-pill')?.classList.contains('ace-note-pill--has-note')"
                )
                page.locator("#note-textarea").fill("")
                page.wait_for_function(
                    "document.querySelector('#ace-notification-receipt')?.textContent === 'Note deleted'"
                )
                assert page.request.get(base + f"/api/source-note/{source_id}").json() == {
                    "note_text": ""
                }
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
