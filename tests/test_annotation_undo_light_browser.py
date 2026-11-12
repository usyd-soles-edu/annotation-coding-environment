"""Same-source annotation undo and redo preserve the rendered text panel."""

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
def test_same_source_undo_redo_keep_text_dom_and_counts(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "undo.ace"
    conn = create_project(str(project), "Undo rendering")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S1", "One sentence.", "row")
    add_source(conn, "S2", "Another sentence.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
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
                page.goto("http://127.0.0.1:8080/code")
                page.evaluate("window.__textPanelBefore = document.getElementById('text-panel')")

                def action(path, values):
                    page.evaluate("""async ({path, values}) => {
                      await htmx.ajax('POST', path, {
                        target: '#text-panel', swap: 'outerHTML', values
                      });
                    }""", {"path": path, "values": values})

                action("/api/code/apply", {
                    "code_id": code_id, "current_index": 0,
                    "start_offset": 0, "end_offset": 3,
                    "selected_text": "One",
                })
                for path, expected_count in (("/api/undo", 0), ("/api/redo", 1)):
                    action(path, {"current_index": 0})
                    page.wait_for_function("""count => {
                      const anns = JSON.parse(document.querySelector('#ace-ann-data')?.dataset.annotations || '[]');
                      const sources = JSON.parse(document.querySelector('#ace-sources-data')?.textContent || '[]');
                      const codeCount = document.querySelector('.ace-ht-count')?.textContent || '';
                      return anns.length === count && sources[0]?.count === count &&
                        codeCount === (count ? String(count) : '');
                    }""", arg=expected_count, timeout=5000)
                    assert page.evaluate(
                        "document.getElementById('text-panel') === window.__textPanelBefore"
                    )

                annotation_id = page.locator("#ace-ann-data").evaluate(
                    "el => JSON.parse(el.dataset.annotations)[0].id"
                )
                page.evaluate("""() => {
                  window.__flashCalls = [];
                  const original = window._flashAnnotation;
                  window._flashAnnotation = id => {
                    window.__flashCalls.push(id);
                    original(id);
                  };
                }""")
                action("/api/code/delete-annotation", {
                    "annotation_id": annotation_id, "current_index": 0,
                })
                action("/api/undo", {"current_index": 0})
                page.wait_for_function(
                    "id => window.__flashCalls.includes(id)",
                    arg=annotation_id, timeout=5000,
                )
                assert page.evaluate(
                    "document.getElementById('text-panel') === window.__textPanelBefore"
                )
            finally:
                browser.close()
