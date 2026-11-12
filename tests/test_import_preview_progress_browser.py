"""Spreadsheet preview progress and cancellation in the import wizard."""

import asyncio
import json
import threading
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

import ace.services.importer as importer
from ace.app import create_app
from ace.db.connection import create_project


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("replace_running_preview", [False, True])
def test_spreadsheet_preview_progress_and_cancel(
    tmp_path, monkeypatch, engine, replace_running_preview
):
    async_api = pytest.importorskip("playwright.async_api")
    project = tmp_path / "preview.ace"
    create_project(str(project), "Preview progress").close()
    csv_path = tmp_path / "large.csv"
    csv_path.write_text(
        "id,text\n" + "".join(f"S{index},Response {index}\n" for index in range(600)),
        encoding="utf-8",
    )
    second_csv_path = tmp_path / "replacement.csv"
    second_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    started = {csv_path: threading.Event(), second_csv_path: threading.Event()}
    release = {csv_path: threading.Event(), second_csv_path: threading.Event()}
    original_scan = importer.scan_tabular_preview

    def held_scan(path, **kwargs):
        report = kwargs["on_progress"]

        def hold_after_first_report(scanned):
            report(scanned)
            if scanned == 256:
                started[path].set()
                assert release[path].wait(10), "preview scan was not released"

        return original_scan(
            path, on_progress=hold_after_first_report,
            should_cancel=kwargs["should_cancel"],
        )

    monkeypatch.setattr(importer, "scan_tabular_preview", held_scan)
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)

        async def exercise():
            pick_count = 0
            first_fulfilled = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, engine).launch()
                try:
                    page = await browser.new_page(viewport={"width": 320, "height": 568})

                    async def serve(route):
                        nonlocal pick_count
                        request = route.request
                        url = urlsplit(request.url)
                        if url.path == "/api/native/pick-file":
                            picked = csv_path if pick_count == 0 else second_csv_path
                            pick_count += 1
                            await route.fulfill(
                                status=200, content_type="application/json",
                                body=json.dumps({"path": str(picked)}),
                            )
                            return
                        path = url.path + (f"?{url.query}" if url.query else "")
                        headers = {
                            key: value for key, value in request.headers.items()
                            if key.lower() not in {"host", "content-length"}
                        }
                        response = await asyncio.to_thread(
                            client.request, request.method, path,
                            content=request.post_data_buffer, headers=headers,
                        )
                        await route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers), body=response.content,
                        )
                        if url.path == "/api/import/file" and parse_qs(
                            request.post_data or ""
                        ).get("path") == [str(csv_path)]:
                            first_fulfilled.set()

                    await page.route("http://127.0.0.1:8080/**", serve)
                    await page.goto("http://127.0.0.1:8080/import")
                    choose = page.locator("#import-spreadsheet-button")
                    await choose.click()
                    assert await asyncio.to_thread(started[csv_path].wait, 5)
                    if replace_running_preview:
                        first_job = app.state.tabular_preview_job
                        await choose.click()
                        # The replacement must start while the first scan is
                        # still held; HTMX body queuing fails this assertion.
                        assert await asyncio.to_thread(started[second_csv_path].wait, 5)
                        assert first_job.cancel.is_set()
                    panel = page.locator("#import-preview-progress")
                    await panel.wait_for(state="visible")
                    await page.wait_for_function("""() =>
                      document.querySelector('[data-import-preview-progress-text]')
                        ?.textContent.includes('256 rows scanned')
                    """)
                    cancel = page.locator("[data-import-preview-cancel]")
                    bounds = await cancel.bounding_box()
                    assert bounds is not None
                    assert 0 <= bounds["x"] and bounds["x"] + bounds["width"] <= 320
                    assert 0 <= bounds["y"] and bounds["y"] + bounds["height"] <= 568
                    await cancel.click()
                    assert await asyncio.to_thread(app.state.tabular_preview_job.cancel.wait, 5)
                    active_path = second_csv_path if replace_running_preview else csv_path
                    release[active_path].set()
                    await page.wait_for_function("""() =>
                      document.querySelector('#import-message')?.textContent ===
                        'Preview cancelled. No sources were added.'
                    """)
                    assert await panel.is_hidden()
                    assert await page.locator("#step-columns").is_hidden()
                    assert app.state.import_stage_token is None
                    if replace_running_preview:
                        release[csv_path].set()
                        await asyncio.wait_for(first_fulfilled.wait(), timeout=5)
                        assert await page.locator("#step-columns").is_hidden()
                        assert await page.locator("#import-message").inner_text() == (
                            "Preview cancelled. No sources were added."
                        )
                finally:
                    for event in release.values():
                        event.set()
                    await browser.close()

        asyncio.run(exercise())
