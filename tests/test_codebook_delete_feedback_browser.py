"""Failed codebook deletion stays visible and can be retried."""

import sqlite3
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
@pytest.mark.parametrize("view", ["coding", "audit"])
def test_failed_delete_reports_error_and_retry_succeeds(tmp_path, engine, view):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "delete-feedback.ace"
    conn = create_project(str(project), "Delete feedback")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "One sentence.", "row")
    audit_code_id = add_code(conn, "Alpha", "#336699")
    delete_code_id = add_code(conn, "Beta", "#663399")
    conn.close()

    app = create_app()
    base = "http://127.0.0.1:8080"
    with TestClient(app, base_url=base) as client:
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
                        headers=dict(response.headers), body=response.content,
                    )

                page.route(f"{base}/**", serve)
                path = "/code" if view == "coding" else f"/code/{audit_code_id}/view"
                page.goto(f"{base}{path}")
                row = page.locator(f'.ace-ht-row[data-code-id="{delete_code_id}"]')
                failed_path = f"{base}/api/codes/{delete_code_id}"
                page.route(
                    f"{failed_path}*",
                    lambda route: route.fulfill(status=503, body="save failed"),
                    times=1,
                )
                row.click(button="right")
                with page.expect_response(
                    lambda response: response.request.method == "DELETE"
                    and urlsplit(response.url).path == f"/api/codes/{delete_code_id}"
                ) as failed:
                    page.get_by_role("menuitem", name="Delete ⌫").click()
                assert failed.value.status == 503
                page.wait_for_function(
                    "document.getElementById('ace-notification-receipt')?.textContent "
                    "=== 'Could not delete item'",
                    timeout=1000,
                )
                assert page.locator("#ace-notification-receipt").is_visible()
                assert row.is_visible()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT deleted_at FROM codebook_code WHERE id = ?", (delete_code_id,)
                    ).fetchone()[0] is None

                row.click(button="right")
                with page.expect_response(
                    lambda response: response.request.method == "DELETE"
                    and urlsplit(response.url).path == f"/api/codes/{delete_code_id}"
                ) as saved:
                    page.get_by_role("menuitem", name="Delete ⌫").click()
                assert saved.value.ok
                page.wait_for_function(
                    "document.getElementById('ace-notification-receipt')?.textContent "
                    "!== 'Could not delete item'"
                )
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT deleted_at FROM codebook_code WHERE id = ?", (delete_code_id,)
                    ).fetchone()[0] is not None
            finally:
                browser.close()
