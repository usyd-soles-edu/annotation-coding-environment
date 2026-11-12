"""The landing page reports picker failures without treating Cancel as an error."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_open_project_picker_failure_and_cancel(engine):
    sync_api = pytest.importorskip("playwright.sync_api")
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
                picker = "**/api/native/pick-file"
                page.route(picker, lambda route: route.fulfill(status=503, json={"path": ""}))
                page.locator("#open-existing-btn").click()
                message = page.locator("#ace-home-message")
                page.wait_for_function(
                    "document.querySelector('#ace-home-message')?.textContent === "
                    "'Could not open the file picker. Try again.'"
                )
                assert message.get_attribute("data-kind") == "err"
                page.wait_for_function("!document.querySelector('#open-existing-btn').disabled")

                page.unroute(picker)
                page.route(picker, lambda route: route.fulfill(json={"path": ""}))
                page.locator("#open-existing-btn").click()
                page.wait_for_function("!document.querySelector('#open-existing-btn').disabled")
                assert message.text_content() == ""
                assert page.url == base + "/"
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
