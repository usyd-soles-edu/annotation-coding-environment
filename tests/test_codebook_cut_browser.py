"""Browser regression for cut state surviving headless tree renders."""

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
def test_cut_ghost_survives_code_and_folder_focus_changes(tmp_path):
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
                browser = playwright.chromium.launch()
            except sync_api.Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip("Playwright Chromium is not installed")
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
                cut_row = page.locator(f'.ace-ht-row[data-item-id="{cut_id}"]')
                codes.nth(1).click()
                assert "ace-code-row--ghost" in cut_row.get_attribute("class")
                assert cut_row.evaluate("el => getComputedStyle(el).opacity") == "0.4"

                page.keyboard.press("Escape")
                assert "ace-code-row--ghost" not in cut_row.get_attribute("class")
                folder = page.locator('.ace-ht-row[data-kind="folder"]').first
                folder.click()
                folder_id = folder.get_attribute("data-item-id")
                page.keyboard.press("Meta+x")
                codes.first.click()
                folder_row = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                assert "ace-code-row--ghost" in folder_row.get_attribute("class")
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
