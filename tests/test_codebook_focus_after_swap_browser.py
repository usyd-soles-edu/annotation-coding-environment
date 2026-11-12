"""Codebook mutations keep keyboard focus when the sidebar is replaced."""

import asyncio
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_codebook_focus_survives_sidebar_swap(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "focus-swap.ace"
    conn = create_project(project, "Focus swap")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    add_code(conn, "Alpha", "#336699")
    beta_id = add_code(conn, "Beta", "#993366")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()

                def serve(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = url.path + (f"?{url.query}" if url.query else "")
                    headers = {
                        key: value for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    }
                    response = client.request(
                        request.method, path,
                        content=request.post_data_buffer, headers=headers,
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers),
                        body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve)
                page.goto("http://127.0.0.1:8080/code")
                beta = page.locator(f'.ace-ht-row[data-item-id="{beta_id}"]')
                beta.wait_for()
                beta.focus()
                page.wait_for_function(
                    "id => document.activeElement?.dataset.itemId === id",
                    arg=beta_id,
                )
                page.evaluate("""async () => {
                    await htmx.ajax('POST', '/api/codes', {
                        target: '#code-sidebar', swap: 'outerHTML',
                        values: {name: 'Gamma', current_index: 0}
                    });
                }""")
                page.wait_for_function(
                    "() => document.querySelector('#code-sidebar')?.textContent.includes('Gamma')"
                )
                page.wait_for_function(
                    "id => document.activeElement?.dataset.itemId === id",
                    arg=beta_id,
                    timeout=3000,
                )
                page.evaluate("""async id => {
                    await htmx.ajax('PUT', `/api/codes/${id}`, {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {colour: '#884466', current_index: 0}
                    });
                }""", beta_id)
                page.wait_for_function("""id => {
                    const row = document.querySelector(`.ace-ht-row[data-item-id="${id}"]`);
                    return row?.style.getPropertyValue('--row-colour') === '#884466';
                }""", arg=beta_id)
                page.wait_for_function(
                    "id => document.activeElement?.dataset.itemId === id",
                    arg=beta_id,
                    timeout=3000,
                )
                search = page.locator("#code-search-input")
                search.fill("Beta")
                search.focus()
                page.evaluate("""async () => {
                    await htmx.ajax('POST', '/api/codes', {
                        target: '#code-sidebar', swap: 'outerHTML',
                        values: {name: 'Delta', current_index: 0}
                    });
                }""")
                page.wait_for_function("""() => Object.values(
                    window.__aceHeadlessTreePreview?.items || {}
                ).some(item => item.name === 'Delta')""")
                page.wait_for_function("""() => {
                    const search = document.getElementById('code-search-input');
                    return document.activeElement === search && search.value === 'Beta';
                }""")
                assert beta.is_visible()
                assert page.locator('.ace-ht-row[aria-label="Delta"]').count() == 0
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_typing_during_tree_reload_is_preserved(tmp_path, engine):
    async_api = pytest.importorskip("playwright.async_api")
    project = tmp_path / "search-reload.ace"
    conn = create_project(project, "Search reload")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    add_code(conn, "Alpha", "#336699")
    add_code(conn, "Beta", "#993366")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id

        async def exercise():
            tree_requests = 0
            reload_started = asyncio.Event()
            release_reload = asyncio.Event()
            async with async_api.async_playwright() as playwright:
                browser = await getattr(playwright, engine).launch()
                try:
                    page = await browser.new_page()

                    async def serve(route):
                        nonlocal tree_requests
                        request = route.request
                        url = urlsplit(request.url)
                        if url.path == "/api/codes/tree":
                            tree_requests += 1
                            if tree_requests == 2:
                                reload_started.set()
                                await release_reload.wait()
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

                    await page.route("http://127.0.0.1:8080/**", serve)
                    await page.goto("http://127.0.0.1:8080/code")
                    await page.locator('.ace-ht-row[aria-label="Beta"]').wait_for()
                    await page.locator("#code-search-input").fill("Beta")
                    mutation = asyncio.create_task(page.evaluate("""() =>
                        htmx.ajax('POST', '/api/codes', {
                            target: '#code-sidebar', swap: 'outerHTML',
                            values: {name: 'Gamma', current_index: 0}
                        })"""))
                    await asyncio.wait_for(reload_started.wait(), timeout=5)
                    search = page.locator("#code-search-input")
                    await search.fill("Alpha")
                    release_reload.set()
                    await mutation
                    await page.wait_for_function("""() => Object.values(
                        window.__aceHeadlessTreePreview?.items || {}
                    ).some(item => item.name === 'Gamma')""")
                    assert await search.input_value() == "Alpha"
                    assert await search.evaluate("el => document.activeElement === el")
                    assert await page.locator('.ace-ht-row[aria-label="Alpha"]').is_visible()
                    assert await page.locator('.ace-ht-row[aria-label="Beta"]').count() == 0
                finally:
                    release_reload.set()
                    await browser.close()

        asyncio.run(exercise())
