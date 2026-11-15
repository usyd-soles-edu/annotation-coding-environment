"""The codebook View action uses the audit view's draft-safe navigation."""

import sqlite3
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
def test_view_menu_preserves_audit_drafts_and_uses_in_place_switch(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "view-menu.ace"
    conn = create_project(str(project), "View menu")
    coder_id = list_coders(conn)[0]["id"]
    source_id = add_source(conn, "Sample", "One sentence.", "row")
    alpha_id = add_code(conn, "Alpha", "#AA0000", definition="Saved alpha")
    beta_id = add_code(conn, "Beta", "#00AA00", definition="Saved beta")
    add_annotation(conn, source_id, coder_id, alpha_id, 0, 3, "One")
    add_annotation(conn, source_id, coder_id, beta_id, 4, 12, "sentence")
    conn.close()

    base = "http://127.0.0.1:8080"
    app = create_app()
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
                page.goto(f"{base}/code/{alpha_id}/view")
                page.locator("#cv-mode-edit").click()
                definition = page.locator("#cv-code-definition")
                definition.fill("Unsaved alpha draft")
                page.evaluate("window.__viewMenuDocument = 'original'")

                def view_from_menu(code_id):
                    page.locator(f'.ace-ht-row[data-code-id="{code_id}"]').click(button="right")
                    page.get_by_role("menu", name="Codebook actions").get_by_role(
                        "menuitem", name="View coded text V"
                    ).click()

                prompts = []

                def dismiss_discard(dialog):
                    prompts.append(dialog.message)
                    dialog.dismiss()

                page.on("dialog", dismiss_discard)

                # Viewing the current code must not reload or prompt away a draft.
                view_from_menu(alpha_id)
                assert prompts == []
                assert page.evaluate("window.__viewMenuDocument") == "original"
                assert definition.input_value() == "Unsaved alpha draft"

                view_from_menu(beta_id)
                assert prompts == ["Discard unsaved code edits?"]
                assert page.url == f"{base}/code/{alpha_id}/view"
                assert definition.input_value() == "Unsaved alpha draft"
                assert page.evaluate("window.__viewMenuDocument") == "original"
                page.wait_for_function(
                    "id => document.activeElement?.dataset.codeId === id",
                    arg=alpha_id,
                )

                page.remove_listener("dialog", dismiss_discard)

                def accept_discard(dialog):
                    prompts.append(dialog.message)
                    dialog.accept()

                page.on("dialog", accept_discard)
                view_from_menu(beta_id)
                page.wait_for_function(
                    "id => document.getElementById('code-view')?.dataset.codeId === id",
                    arg=beta_id,
                )
                assert prompts == ["Discard unsaved code edits?"] * 2
                assert page.url == f"{base}/code/{beta_id}/view"
                assert page.evaluate("window.__viewMenuDocument") == "original"
                page.wait_for_function(
                    "id => document.activeElement?.dataset.codeId === id",
                    arg=beta_id,
                )
                with sqlite3.connect(project) as saved:
                    assert saved.execute(
                        "SELECT definition FROM codebook_code WHERE id = ?", (alpha_id,)
                    ).fetchone()[0] == "Saved alpha"

                # The coding-page menu still enters the audit view by navigation.
                page.goto(f"{base}/code")
                view_from_menu(alpha_id)
                assert page.url == f"{base}/code/{alpha_id}/view"

                page.goto(f"{base}/code")
                page.locator("#ace-headless-tree-mount").evaluate(
                    "mount => mount.dataset.codebookMode = 'readonly'"
                )
                view_from_menu(beta_id)
                assert page.url == f"{base}/code/{beta_id}/view"
            finally:
                browser.close()
