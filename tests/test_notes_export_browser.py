"""Empty source-note exports report the absence of notes instead of success."""

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
def test_export_notes_feedback_matches_download(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Notes export")
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
                page = browser.new_page(accept_downloads=True)
                page.goto(base + "/")
                assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
                page.goto(base + "/code")
                page.locator("#codebook-menu-btn").click()
                page.locator("#export-notes-btn").click()
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent === 'No notes to export'"
                )
                assert page.locator(".ace-statusbar-event--ok-sticky").count() == 1

                saved = page.request.put(
                    base + f"/api/source-note/{source_id}",
                    form={"note_text": "A source note"},
                )
                assert saved.ok
                page.locator("#codebook-menu-btn").click()
                with page.expect_download() as info:
                    page.locator("#export-notes-btn").click()
                assert info.value.suggested_filename.endswith(".csv")
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent === 'Exported'"
                )

                export_requests = []
                downloads = []
                page.on("request", lambda request: export_requests.append(request.method)
                        if request.url.endswith("/api/export/notes") else None)
                page.on("download", lambda download: downloads.append(download))
                page.route(
                    f"**/api/source-note/{source_id}",
                    lambda route: route.fulfill(status=500, body="save failed"),
                )
                page.locator("#note-pill").click()
                page.locator("#note-pill").click()
                page.locator("#note-textarea").fill("Unsaved replacement")
                page.locator("#codebook-menu-btn").click()
                page.locator("#export-notes-btn").click()
                page.wait_for_function(
                    "document.querySelector('.ace-statusbar-event')?.textContent === 'Could not export source notes'"
                )
                assert export_requests == []
                assert downloads == []
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
