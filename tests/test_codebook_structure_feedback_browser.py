"""Codebook structural edits report server failures and remain retryable."""

import sqlite3
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("view", ["coding", "audit"])
@pytest.mark.parametrize(
    ("operation", "suffix", "method", "message"),
    [
        ("moveItemToParent", "/parent", "PUT", "Could not move item"),
        ("convertItemToFolder", "/convert-to-folder", "POST", "Could not convert code"),
        ("wrapSiblingCodes", "/indent-promote", "POST", "Could not create folder"),
    ],
)
def test_failed_structure_edit_reports_error_and_retry_succeeds(
    tmp_path, engine, view, operation, suffix, method, message,
):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "structure-feedback.ace"
    conn = create_project(str(project), "Structure feedback")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "Sample", "One sentence.", "row")
    alpha_id = add_code(conn, "Alpha", "#336699")
    beta_id = add_code(conn, "Beta", "#663399")
    folder_id = add_folder(conn, "Group")
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
                path = "/code" if view == "coding" else f"/code/{alpha_id}/view"
                page.goto(f"{base}{path}")
                row = page.locator(f'.ace-ht-row[data-code-id="{beta_id}"]')
                row.wait_for()
                endpoint = f"{base}/api/codes/{beta_id}{suffix}"
                page.route(
                    endpoint, lambda route: route.fulfill(status=503, body="save failed"),
                    times=1,
                )

                def request_edit():
                    page.evaluate(
                        "([action, item, folder, sibling]) => {"
                        " const controller = window.AceHeadlessTreePreview.getController();"
                        " if (action === 'moveItemToParent') controller.moveItemToParent(item, folder);"
                        " else if (action === 'wrapSiblingCodes') controller.wrapSiblingCodes(item, sibling);"
                        " else controller.convertItemToFolder(item);"
                        "}",
                        [operation, beta_id, folder_id, alpha_id],
                    )

                predicate = lambda response: (
                    response.request.method == method
                    and urlsplit(response.url).path == f"/api/codes/{beta_id}{suffix}"
                )
                with page.expect_response(predicate) as failed:
                    request_edit()
                assert failed.value.status == 503
                page.wait_for_function(
                    "message => document.getElementById('ace-notification-receipt')"
                    "?.textContent === message",
                    arg=message, timeout=1000,
                )
                assert page.locator("#ace-notification-receipt").is_visible()
                assert row.is_visible()
                with sqlite3.connect(project) as stored:
                    assert stored.execute(
                        "SELECT kind, parent_id FROM codebook_code WHERE id = ?", (beta_id,)
                    ).fetchone() == ("code", None)

                with page.expect_response(predicate) as saved:
                    request_edit()
                assert saved.value.ok
                page.wait_for_function(
                    "message => document.getElementById('ace-notification-receipt')"
                    "?.textContent !== message",
                    arg=message,
                )
                with sqlite3.connect(project) as stored:
                    kind, parent_id = stored.execute(
                        "SELECT kind, parent_id FROM codebook_code WHERE id = ?", (beta_id,)
                    ).fetchone()
                    if operation == "moveItemToParent":
                        assert (kind, parent_id) == ("code", folder_id)
                    elif operation == "convertItemToFolder":
                        assert (kind, parent_id) == ("folder", None)
                    else:
                        assert kind == "code" and parent_id is not None
                        assert stored.execute(
                            "SELECT parent_id FROM codebook_code WHERE id = ?", (alpha_id,)
                        ).fetchone()[0] == parent_id
            finally:
                browser.close()
