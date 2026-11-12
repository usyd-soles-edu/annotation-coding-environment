"""A long tabular import stays responsive and can be cancelled from the UI."""

import socket
import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn

import ace.services.importer as importer
from ace.app import create_app
from ace.db.connection import create_project, open_project
from ace.models.source import list_sources


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_import_progress_and_cancel_in_browser(tmp_path, monkeypatch, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "progress.ace"
    create_project(str(project), "Progress").close()
    csv_path = tmp_path / "responses.csv"
    csv_path.write_text("id,text\nA,first\nB,second\nC,third\n", encoding="utf-8")

    inserted = threading.Event()
    release = threading.Event()
    original_add = importer._add_source_no_commit

    def pause_after_first_insert(conn, **kwargs):
        source_id = original_add(conn, **kwargs)
        inserted.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Test import was not released")
        return source_id

    monkeypatch.setattr(importer, "_add_source_no_commit", pause_after_first_insert)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    server_thread = threading.Thread(target=server.run)
    server_thread.start()
    try:
        deadline = time.monotonic() + 8
        while True:
            try:
                with urlopen(base + "/", timeout=0.5):
                    break
            except OSError:
                if not server_thread.is_alive() or time.monotonic() >= deadline:
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
                assert page.request.post(
                    base + "/api/project/open", form={"path": str(project)}
                ).ok
                page.goto(base + "/import")
                page.evaluate("""path => {
                    htmx.ajax('POST', '/api/import/file', {
                        values: {path}, target: '#step-columns', swap: 'innerHTML'
                    });
                    showStep('step-columns');
                }""", str(csv_path))
                page.locator("#import-submit").wait_for()
                page.locator("#import-submit").click()
                assert inserted.wait(timeout=5)
                panel = page.locator("#import-progress")
                panel.wait_for(state="visible")
                assert page.locator("[data-import-progress-text]").is_visible()
                assert page.locator("[data-import-back]").is_disabled()
                page.set_viewport_size({"width": 320, "height": 568})
                cancel_box = page.locator("[data-import-cancel]").bounding_box()
                assert cancel_box is not None
                assert 0 <= cancel_box["x"]
                assert cancel_box["x"] + cancel_box["width"] <= 320
                assert 0 <= cancel_box["y"]
                assert cancel_box["y"] + cancel_box["height"] <= 568
                page.locator("[data-import-cancel]").click()
                assert app.state.tabular_import_job.cancel.wait(timeout=5)
                release.set()
                page.wait_for_function(
                    "document.querySelector('#import-message')?.textContent === "
                    "'Import cancelled. No sources were added.'"
                )
                assert panel.is_hidden()
                assert page.locator("#import-submit").is_enabled()
                assert page.locator("#step-columns").is_visible()
            finally:
                browser.close()
    finally:
        release.set()
        server.should_exit = True
        server_thread.join(timeout=5)

    assert not server_thread.is_alive()
    conn = open_project(str(project))
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()
