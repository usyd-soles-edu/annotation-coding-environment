"""A late preview response cannot hide a newer spreadsheet mapping."""

import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_stale_preview_finishes_before_current_preview(tmp_path, engine):
    async_api = pytest.importorskip("playwright.async_api")
    project = tmp_path / "preview.ace"
    create_project(str(project), "Preview race").close()
    first_file = tmp_path / "first.csv"
    second_file = tmp_path / "second.csv"
    first_file.write_text("id,text\nA,First response\n", encoding="utf-8")
    second_file.write_text("id,text\nB,Second response\n", encoding="utf-8")

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)

        async def exercise():
            pick_count = 0
            first_started = asyncio.Event()
            second_started = asyncio.Event()
            release_first = asyncio.Event()
            release_second = asyncio.Event()
            first_finished = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, engine).launch()
                try:
                    page = await browser.new_page()

                    async def serve_from_test_client(route):
                        nonlocal pick_count
                        request = route.request
                        url = urlsplit(request.url)
                        if url.path == "/api/native/pick-file":
                            selected = first_file if pick_count == 0 else second_file
                            pick_count += 1
                            await route.fulfill(
                                status=200,
                                content_type="application/json",
                                body=json.dumps({"path": str(selected)}),
                            )
                            return
                        if url.path == "/api/import/file":
                            form = parse_qs(request.post_data or "")
                            if form.get("path") == [str(first_file)]:
                                first_started.set()
                                await release_first.wait()
                                await route.fulfill(status=409, body="Preview superseded")
                                first_finished.set()
                                return
                            second_started.set()
                            await release_second.wait()
                        path = url.path + (f"?{url.query}" if url.query else "")
                        headers = {
                            key: value for key, value in request.headers.items()
                            if key.lower() not in {"host", "content-length"}
                        }
                        response = client.request(
                            request.method, path,
                            content=request.post_data_buffer, headers=headers,
                        )
                        await route.fulfill(
                            status=response.status_code,
                            headers=dict(response.headers),
                            body=response.content,
                        )

                    await page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                    await page.goto("http://127.0.0.1:8080/import")
                    button = page.locator("#import-spreadsheet-button")
                    await button.click()
                    await asyncio.wait_for(first_started.wait(), timeout=5)
                    await button.click()
                    assert pick_count == 2
                    release_first.set()
                    await asyncio.wait_for(first_finished.wait(), timeout=5)
                    assert await page.locator("#step-columns").is_hidden()
                    await asyncio.wait_for(second_started.wait(), timeout=5)
                    release_second.set()
                    await page.locator("#import-submit").wait_for(state="visible")
                    assert "Second response" in await page.locator("#step-columns").inner_text()
                finally:
                    release_first.set()
                    release_second.set()
                    await browser.close()

        asyncio.run(exercise())
