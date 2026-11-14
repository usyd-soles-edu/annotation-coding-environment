"""Opening codebook import twice must not spawn two native file pickers."""

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
@pytest.mark.parametrize("mode", ["coding", "audit"])
def test_import_waits_for_existing_file_picker(tmp_path, engine, mode):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "picker.ace"
    conn = create_project(str(project), "Picker")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One source.", "row")
    code_id = add_code(conn, "Current", "#AA0000")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})

                def serve_from_test_client(route):
                    request = route.request
                    url = urlsplit(request.url)
                    path = url.path + (f"?{url.query}" if url.query else "")
                    headers = {
                        key: value for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    }
                    response = client.request(
                        request.method, path, content=request.post_data_buffer, headers=headers
                    )
                    route.fulfill(
                        status=response.status_code,
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve_from_test_client)
                page.goto(
                    f"http://127.0.0.1:8080/code/{code_id}/view"
                    if mode == "audit" else "http://127.0.0.1:8080/code"
                )
                page.evaluate("""() => {
                    const nativeFetch = window.fetch.bind(window);
                    window.__acePickerCalls = 0;
                    window.fetch = (url, options) => {
                        if (url !== '/api/native/pick-file') return nativeFetch(url, options);
                        window.__acePickerCalls += 1;
                        return new Promise(resolve => {
                            window.__releasePicker = (status = 200) => resolve({
                                ok: status >= 200 && status < 300,
                                json: async () => ({path: null})
                            });
                        });
                    };
                }""")

                menu = page.locator("#codebook-menu-btn")
                item = page.locator("#codebook-menu-import-btn")
                menu.click()
                item.click()
                assert page.evaluate("window.__acePickerCalls") == 1
                menu.click()
                item.click()
                assert page.evaluate("window.__acePickerCalls") == 1

                page.evaluate("""async () => {
                    window.__releasePicker();
                    await new Promise(resolve => setTimeout(resolve, 0));
                }""")
                menu.click()
                item.click()
                assert page.evaluate("window.__acePickerCalls") == 2
                page.evaluate("""async () => {
                    window.__releasePicker(503);
                    await new Promise(resolve => setTimeout(resolve, 0));
                }""")
                page.wait_for_function("""() =>
                    document.getElementById('ace-statusbar')?.textContent
                        .includes('Could not open file picker')
                """)
                menu.click()
                item.click()
                assert page.evaluate("window.__acePickerCalls") == 3
                page.evaluate("window.__releasePicker()")
            finally:
                browser.close()
