"""Warn when two same-origin tabs can edit the current codebook."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("browser_name", ["chromium", "firefox", "webkit"])
def test_two_codebook_tabs_warn_until_one_closes(tmp_path, browser_name):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "two-tabs.ace"
    conn = create_project(str(project), "Two tabs")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "Source text.", "row")
    code_id = add_code(conn, "Example", "#336699")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            try:
                browser = getattr(playwright, browser_name).launch()
            except sync_api.Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip(f"Playwright {browser_name} is not installed")
                raise
            try:
                context = browser.new_context()

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
                        headers=dict(response.headers),
                        body=response.content,
                    )

                context.route("http://127.0.0.1:8080/**", serve_from_test_client)
                first = context.new_page()
                first.goto("http://127.0.0.1:8080/code")
                warning = first.locator(".ace-codebook-tab-warning")
                assert not warning.is_visible()

                second = context.new_page()
                second.goto("http://127.0.0.1:8080/code")
                warning.wait_for(state="visible")
                second.locator(".ace-codebook-tab-warning").wait_for(state="visible")

                # Playwright's fulfilled attachment navigation destroys the
                # intercepted WebKit page. Check this path in the other two
                # engines; real Safari uses a running HTTP server instead.
                if browser_name != "webkit":
                    with first.expect_download():
                        first.evaluate("window.location.href = '/api/codes/export'")
                    assert warning.is_visible()

                # Replacing the sidebar must not make the warning disappear.
                first.evaluate("""() => htmx.ajax('POST', '/api/codes/folder', {
                    target: '#text-panel', swap: 'outerHTML',
                    values: { name: 'New folder', current_index: 0 }
                })""")
                first.get_by_text("New folder", exact=True).wait_for()
                assert warning.is_visible()

                second.close()
                first.reload()
                warning.wait_for(state="hidden")

                # The audit page has the same editable codebook and must
                # participate in the same warning.
                audit = context.new_page()
                audit.goto(f"http://127.0.0.1:8080/code/{code_id}/view")
                warning.wait_for(state="visible")
                audit.locator(".ace-codebook-tab-warning").wait_for(state="visible")
            finally:
                browser.close()
