"""Same-source annotation undo and redo preserve the rendered text panel."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
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
    other_source_id = add_source(conn, "S2", "Another sentence.", "row")
    code_id = add_code(conn, "Alpha", "#336699")
    other_code_id = add_code(conn, "Beta", "#993366")
    add_annotation(conn, other_source_id, coder_id, other_code_id, 0, 7, "Another")
    conn.close()

    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                context = browser.new_context()
                page = context.new_page()

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
                    page.wait_for_function("""({count, codeId, otherCodeId}) => {
                      const anns = JSON.parse(document.querySelector('#ace-ann-data')?.dataset.annotations || '[]');
                      const tileCount = document.querySelector('.ace-grid-tile[data-source-index="0"]')?.dataset.count;
                      const sourcePatch = document.querySelector('#ace-ann-data')?.dataset.sourcePatchCount;
                      const codeCount = document.querySelector(
                        `.ace-ht-row[data-item-id="${codeId}"] .ace-ht-count`
                      )?.textContent || '';
                      const otherCount = document.querySelector(
                        `.ace-ht-row[data-item-id="${otherCodeId}"] .ace-ht-count`
                      )?.textContent || '';
                      return anns.length === count && tileCount === String(count) &&
                        sourcePatch === String(count) &&
                        document.querySelector('.ace-grid-tile[data-source-index="1"]')?.dataset.count === '1' &&
                        otherCount === '1' &&
                        codeCount === (count ? String(count) : '');
                    }""", arg={
                        "count": expected_count,
                        "codeId": code_id,
                        "otherCodeId": other_code_id,
                    }, timeout=5000)
                    assert page.evaluate(
                        "document.getElementById('text-panel') === window.__textPanelBefore"
                    )

                collapse = page.locator("#ace-grid-collapse-btn")
                collapse.click()
                collapse.click()
                assert page.locator(
                    '.ace-grid-tile[data-source-index="0"]'
                ).get_attribute("data-count") == "1"
                assert page.locator(
                    '.ace-grid-tile[data-source-index="1"]'
                ).get_attribute("data-count") == "1"

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

                # The second response swaps before the first settles. Both
                # changed code counts must survive their separate OOB patches.
                page.evaluate("""({annotationId, otherCodeId}) => {
                  htmx.config.defaultSettleDelay = 300;
                  let launched = false;
                  document.addEventListener('htmx:oobAfterSwap', evt => {
                    const detail = evt.detail || {};
                    const isAnnData = [detail.target, detail.elt, evt.target]
                      .some(el => el && el.id === 'ace-ann-data');
                    if (!isAnnData || launched) return;
                    launched = true;
                    setTimeout(() => htmx.ajax('POST', '/api/code/apply', {
                      target: '#text-panel', swap: 'outerHTML',
                      values: {
                        code_id: otherCodeId, current_index: 0,
                        start_offset: 4, end_offset: 12,
                        selected_text: 'sentence'
                      }
                    }), 0);
                  });
                  htmx.ajax('POST', '/api/code/delete-annotation', {
                    target: '#text-panel', swap: 'outerHTML',
                    values: {annotation_id: annotationId, current_index: 0}
                  });
                }""", {"annotationId": annotation_id, "otherCodeId": other_code_id})
                page.wait_for_function("""({codeId, otherCodeId}) => {
                  const a = document.querySelector(
                    `.ace-ht-row[data-item-id="${codeId}"] .ace-ht-count`
                  )?.textContent || '';
                  const b = document.querySelector(
                    `.ace-ht-row[data-item-id="${otherCodeId}"] .ace-ht-count`
                  )?.textContent || '';
                  return a === '' && b === '2' &&
                    document.querySelector('.ace-grid-tile[data-source-index="0"]')?.dataset.count === '1';
                }""", arg={"codeId": code_id, "otherCodeId": other_code_id}, timeout=5000)

                page.evaluate("window.__gridBefore = document.getElementById('ace-grid-tiles')")
                page.evaluate("""async () => {
                  await htmx.ajax('POST', '/api/codes', {
                    target: '#code-sidebar', swap: 'outerHTML',
                    values: {name: 'Gamma', current_index: 0}
                  });
                }""")
                page.wait_for_function("""() => {
                  const grid = document.getElementById('ace-grid-tiles');
                  return grid !== window.__gridBefore &&
                    grid.querySelector('.ace-grid-tile[data-source-index="0"]')?.dataset.count === '1' &&
                    document.querySelector('#code-sidebar')?.textContent.includes('Gamma');
                }""", timeout=5000)

                # Another tab's edit dirties this tab's project-wide counts.
                # Its next annotation action refreshes the whole snapshot.
                page.evaluate("""() => {
                  window.__countBroadcasts = 0;
                  window.__countWatch = new BroadcastChannel('ace-annotation-counts');
                  window.__countWatch.onmessage = () => window.__countBroadcasts++;
                }""")
                other_page = context.new_page()
                other_page.route("http://127.0.0.1:8080/**", serve)
                other_page.goto("http://127.0.0.1:8080/code?index=1")
                other_page.evaluate("""async codeId => {
                  await htmx.ajax('POST', '/api/code/apply', {
                    target: '#text-panel', swap: 'outerHTML',
                    values: {
                      code_id: codeId, current_index: 1,
                      start_offset: 8, end_offset: 16,
                      selected_text: 'sentence'
                    }
                  });
                }""", other_code_id)
                other_page.wait_for_function("""() =>
                  document.querySelector('.ace-grid-tile[data-source-index="1"]')?.dataset.count === '2'
                """, timeout=5000)
                page.wait_for_function("window.__countBroadcasts > 0", timeout=5000)
                action("/api/code/apply", {
                    "code_id": code_id, "current_index": 0,
                    "start_offset": 0, "end_offset": 3,
                    "selected_text": "One",
                })
                page.wait_for_function("""otherCodeId => {
                  const otherCount = document.querySelector(
                    `.ace-ht-row[data-item-id="${otherCodeId}"] .ace-ht-count`
                  )?.textContent;
                  return otherCount === '3' &&
                    document.querySelector('.ace-grid-tile[data-source-index="1"]')?.dataset.count === '2' &&
                    document.querySelector('#ace-ann-data')?.dataset.countRefreshVersion === '1';
                }""", arg=other_code_id, timeout=5000)
                page.evaluate("window.__countWatch.close()")

                # X on a stale sentence must clear the old highlight even if
                # the other tab has already removed its last annotation.
                page.goto("http://127.0.0.1:8080/code?index=1")
                page.evaluate("""() => {
                  window.__countBroadcasts = 0;
                  window.__countWatch = new BroadcastChannel('ace-annotation-counts');
                  window.__countWatch.onmessage = () => window.__countBroadcasts++;
                }""")
                for expected in (1, 0):
                    other_page.evaluate("""async () => {
                      await htmx.ajax('POST', '/api/code/delete-sentence', {
                        target: '#text-panel', swap: 'outerHTML',
                        values: {sentence_index: 0, current_index: 1}
                      });
                    }""")
                    other_page.wait_for_function("""count =>
                      document.querySelector('.ace-grid-tile[data-source-index="1"]')?.dataset.count === String(count)
                    """, arg=expected, timeout=5000)
                page.wait_for_function("window.__countBroadcasts >= 2", timeout=5000)
                action("/api/code/delete-sentence", {
                    "sentence_index": 0, "current_index": 1,
                })
                page.wait_for_function("""otherCodeId => {
                  const annData = document.querySelector('#ace-ann-data');
                  const otherCount = document.querySelector(
                    `.ace-ht-row[data-item-id="${otherCodeId}"] .ace-ht-count`
                  )?.textContent;
                  return JSON.parse(annData?.dataset.annotations || '[]').length === 0 &&
                    annData?.dataset.countRefreshVersion === '2' &&
                    document.querySelector('.ace-grid-tile[data-source-index="1"]')?.dataset.count === '0' &&
                    otherCount === '1';
                }""", arg=other_code_id, timeout=5000)
                page.evaluate("window.__countWatch.close()")
                other_page.close()
            finally:
                browser.close()
