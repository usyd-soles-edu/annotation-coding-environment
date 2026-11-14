"""Audit codebook focus stays with the shared tree through zone changes."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_audit_codebook_focus_survives_zone_changes(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "audit-focus.ace"
    conn = create_project(str(project), "Audit focus")
    coder_id = list_coders(conn)[0]["id"]
    source_id = add_source(conn, "S1", "Alpha beta.", "row")
    alpha_id = add_code(conn, "Alpha", "#AA0000")
    beta_id = add_code(conn, "Beta", "#0000AA")
    folder_id = add_folder(conn, "Empty folder")
    add_annotation(conn, source_id, coder_id, alpha_id, 0, 5, "Alpha")
    add_annotation(conn, source_id, coder_id, beta_id, 6, 10, "beta")
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
                        headers=dict(response.headers), body=response.content,
                    )

                page.route("http://127.0.0.1:8080/**", serve)
                page.goto(f"http://127.0.0.1:8080/code/{alpha_id}/view")
                beta = page.locator(f'.ace-ht-row[data-item-id="{beta_id}"]')
                beta.wait_for()

                def assert_tree_focus(code_id):
                    page.wait_for_function("""id => {
                        const row = document.querySelector(`.ace-ht-row[data-item-id="${id}"]`);
                        const focused = window.__aceHeadlessTreePreview?.tree?.getFocusedItem?.();
                        return row?.tabIndex === 0 && document.activeElement === row
                            && focused?.getId() === id;
                    }""", arg=code_id)

                assert_tree_focus(alpha_id)
                beta.click()
                page.wait_for_function(
                    "id => document.getElementById('code-view')?.dataset.codeId === id",
                    arg=beta_id,
                )
                assert_tree_focus(beta_id)

                page.locator(".cv-track-row").first.focus()
                page.keyboard.press("ArrowLeft")
                assert_tree_focus(beta_id)

                page.locator("#code-search-input").fill("Alpha")
                page.locator(f'.ace-ht-row[data-item-id="{beta_id}"]').wait_for(state="detached")
                page.locator(".cv-track-row").first.focus()
                page.keyboard.press("ArrowLeft")
                assert_tree_focus(alpha_id)
                assert page.locator("#code-view").get_attribute("data-code-id") == beta_id

                page.locator("#code-search-input").fill("Empty folder")
                folder = page.locator(f'.ace-ht-row[data-item-id="{folder_id}"]')
                folder.wait_for()
                folder.click()
                assert_tree_focus(folder_id)
                page.locator(".cv-track-row").first.focus()
                page.keyboard.press("ArrowLeft")
                assert_tree_focus(folder_id)
                assert page.locator("#code-view").get_attribute("data-code-id") == beta_id

                page.evaluate("sessionStorage.setItem('cv-restore-codebook-focus', '1')")
                page.goto(f"http://127.0.0.1:8080/code/{beta_id}/view")
                assert_tree_focus(beta_id)
                assert page.evaluate(
                    "sessionStorage.getItem('cv-restore-codebook-focus')"
                ) is None
            finally:
                browser.close()
