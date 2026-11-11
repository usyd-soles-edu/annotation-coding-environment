"""The per-source controls remain visible while reading a long source."""

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
def test_source_header_stays_visible_after_scrolling(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "long-source.ace"
    conn = create_project(str(path), "Long source")
    add_source(conn, "S1", "This is a sentence in a long source. " * 90, "row")
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
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(base + "/")
                assert page.request.post(base + "/api/project/open", form={"path": str(path)}).ok
                page.goto(base + "/code")
                scroll = page.locator("#text-scroll")
                assert scroll.evaluate("el => el.scrollHeight > el.clientHeight * 2")
                page.evaluate("window._setStatus('Saved', 'ok-sticky')")

                def receipt_in_view():
                    return page.evaluate("""() => {
                      const scroll = document.querySelector('#text-scroll').getBoundingClientRect();
                      const receipt = document.querySelector('#ace-notification-receipt').getBoundingClientRect();
                      return receipt.top >= scroll.top && receipt.bottom <= scroll.bottom;
                    }""")

                assert receipt_in_view(), "the notification pill is hidden at the top of a long source"
                scroll.evaluate("el => { el.scrollTop = el.scrollHeight; }")
                page.wait_for_function("document.querySelector('#text-scroll').scrollTop > 500")
                assert receipt_in_view(), "the notification pill is hidden at the end of a long source"
                bounds = page.evaluate("""() => {
                  const scroll = document.querySelector('#text-scroll').getBoundingClientRect();
                  const header = document.querySelector('.ace-text-header').getBoundingClientRect();
                  return {scrollTop: scroll.top, headerTop: header.top,
                    headerBottom: header.bottom};
                }""")
                assert bounds["headerTop"] >= bounds["scrollTop"] - 1, bounds
                assert bounds["headerBottom"] < 800
                target = page.locator(".ace-sentence").nth(10)
                target.evaluate("el => el.scrollIntoView({block: 'nearest'})")
                assert target.evaluate("el => el.getClientRects()[0].top") >= page.locator(
                    ".ace-text-header"
                ).evaluate("el => el.getBoundingClientRect().bottom")
                flag = page.locator("#nav-flag-btn")
                flag.click()
                page.wait_for_function("document.querySelector('#nav-flag-btn').getAttribute('aria-pressed') === 'true'")
                assert page.locator("#note-pill").is_visible()
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
