"""Browser regression for UTF-16 DOM and codepoint source offsets."""

import os
import socket
import sqlite3
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
def test_unicode_selection_and_highlight_round_trip(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "unicode.ace"
    source_text = "😀 ABC.  😀 DEF."
    conn = create_project(str(path), "Unicode offsets")
    source_id = add_source(conn, "S1", source_text, "row")
    coder_id = list_coders(conn)[0]["id"]
    initial_code = add_code(conn, "Sentence", "#AA0000")
    after_code = add_code(conn, "After emoji", "#00AA00")
    across_code = add_code(conn, "Across sentences", "#0000AA")
    add_annotation(conn, source_id, coder_id, initial_code, 0, 6, "😀 ABC.")
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
                page.goto(base + "/code")
                page.locator("rect[data-ace-hl]").first.wait_for()
                result = page.evaluate("""() => {
                  const sentences = document.querySelectorAll('.ace-sentence');
                  const first = sentences[0].firstChild;
                  const second = sentences[1].firstChild;
                  const selection = window.getSelection();
                  function capture(startNode, start, endNode, end) {
                    const range = document.createRange();
                    range.setStart(startNode, start);
                    range.setEnd(endNode, end);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    return {...window.__aceLastSelection};
                  }
                  const full = document.createRange();
                  full.setStart(first, 0);
                  full.setEnd(first, 7);
                  const expectedWidth = full.getBoundingClientRect().width;
                  const paintedWidth = Number(document.querySelector('rect[data-ace-hl]').getAttribute('width'));
                  const before = capture(first, 0, first, 2);
                  const after = capture(first, 3, first, 6);
                  const across = capture(first, 3, second, 6);
                  const tail = first.splitText(3);
                  const mixed = capture(tail, 0, tail, 3);
                  return {before, after, across, mixed, expectedWidth, paintedWidth};
                }""")
                assert (result["before"]["start"], result["before"]["end"]) == (0, 1)
                assert (result["after"]["start"], result["after"]["end"]) == (2, 5)
                assert (result["across"]["start"], result["across"]["end"]) == (2, 13)
                assert (result["mixed"]["start"], result["mixed"]["end"]) == (2, 5)
                assert abs(result["paintedWidth"] - result["expectedWidth"]) < 2

                for code_id, selection in (
                    (after_code, result["after"]),
                    (across_code, result["across"]),
                ):
                    response = page.request.post(base + "/api/code/apply", form={
                        "code_id": code_id,
                        "start_offset": selection["start"],
                        "end_offset": selection["end"],
                        "selected_text": selection["text"],
                    })
                    assert response.ok
            finally:
                browser.close()

        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "SELECT code_id, start_offset, end_offset, selected_text "
                "FROM annotation WHERE code_id IN (?, ?) ORDER BY start_offset, end_offset",
                (after_code, across_code),
            ).fetchall()
            assert rows == [
                (after_code, 2, 5, "ABC"),
                (across_code, 2, 13, "ABC.  😀 DEF"),
            ]
        finally:
            conn.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
