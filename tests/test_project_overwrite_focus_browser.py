"""Closing the HTMX-loaded overwrite dialog returns focus to Create project."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_overwrite_dialog_restores_create_button_focus(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    existing = tmp_path / "Existing.ace"
    create_project(str(existing), "Existing").close()

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
                page.goto(base + "/new-project")
                page.route(
                    "**/api/native/pick-folder",
                    lambda route: route.fulfill(json={"path": str(tmp_path)}),
                )
                page.locator("#new-project-input").fill("Existing")
                page.locator("#choose-project-folder-btn").click()
                create_button = page.locator("#create-project-btn")
                page.wait_for_function(
                    "!document.querySelector('#create-project-btn').disabled"
                )
                create_button.click()
                dialog = page.locator("#project-overwrite-dialog")
                dialog.wait_for(state="visible")
                assert dialog.evaluate("el => el.matches(':modal')")
                page.keyboard.press("Escape")
                dialog.wait_for(state="hidden")
                page.wait_for_function(
                    "document.activeElement === document.querySelector('#create-project-btn')",
                )

                name_input = page.locator("#new-project-input")
                name_input.focus()
                name_input.press("Enter")
                dialog.wait_for(state="visible")
                page.keyboard.press("Escape")
                dialog.wait_for(state="hidden")
                page.wait_for_function(
                    "document.activeElement === document.querySelector('#new-project-input')",
                )
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
