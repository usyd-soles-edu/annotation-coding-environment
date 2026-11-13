"""Source resume follows the project file across authenticated desktop ports."""

import os
import shutil
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import quote, urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import checkpoint_and_close, create_project
from ace.models.project import get_project, list_coders
from ace.models.source import add_source
from ace.services.shared_source_position import position_key


def _route_to(client):
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
    return serve


def _make_project(path):
    conn = create_project(str(path), "Source position")
    coder_id = list_coders(conn)[0]["id"]
    project_id = get_project(conn)["id"]
    for label in ("First", "Second", "Third"):
        add_source(conn, label, f"{label} source text.", "row")
    checkpoint_and_close(conn)
    return position_key(str(path), project_id, coder_id), project_id


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_source_position_shares_across_ports_but_not_copied_projects(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "project.ace"
    copy = tmp_path / "copy.ace"
    legacy = tmp_path / "legacy.ace"
    _, project_id = _make_project(project)
    shutil.copy2(project, copy)  # Same project ID, distinct file identity.
    legacy_key, _ = _make_project(legacy)
    base_a = "http://127.0.0.1:18131"
    base_b = "http://127.0.0.1:18132"

    with ExitStack() as stack:
        clients = []
        for port, token in ((18131, "position-a"), (18132, "position-b")):
            env = {
                "ACE_LAUNCHER_TOKEN": token,
                "ACE_RUNTIME_FILE": str(tmp_path / f"runtime-{port}.json"),
                "ACE_IDLE_TIMEOUT_SECONDS": "300",
            }
            with patch.dict(os.environ, env, clear=False):
                clients.append(stack.enter_context(TestClient(
                    create_app(), base_url=f"http://127.0.0.1:{port}"
                )))

        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page()
                page.route(base_a + "/**", _route_to(clients[0]))
                page.route(base_b + "/**", _route_to(clients[1]))
                page.goto(base_a + "/launch?token=position-a")
                page.evaluate(
                    "key => localStorage.setItem(key, '2')",
                    "ace-source-index:" + project_id,
                )
                page.goto(base_a + "/code?open=" + quote(str(project)))
                assert page.evaluate("window.__aceCurrentIndex") == 0
                with page.expect_response(
                    lambda r: r.url.endswith("/api/navigation")
                    and r.status == 200
                ):
                    page.evaluate("window.aceNavigate(1)")
                page.wait_for_function("window.__aceCurrentIndex === 1")

                page.goto(base_b + "/launch?token=position-b")
                page.goto(base_b + "/code?open=" + quote(str(project)))
                assert page.evaluate("window.__aceCurrentIndex") == 1
                assert "Second source text." in page.locator("#text-panel").inner_text()

                page.goto(base_b + "/code?open=" + quote(str(copy)))
                assert page.evaluate("window.__aceCurrentIndex") == 0
                assert "First source text." in page.locator("#text-panel").inner_text()

                # Migrate a path-scoped browser position only if no desktop
                # runtime has already chosen a source for that project.
                page.goto(base_a + "/")
                page.evaluate(
                    "key => localStorage.setItem(key, '2')",
                    "ace-source-index:" + legacy_key,
                )
                with page.expect_response(
                    lambda r: r.url.endswith("/api/runtime/source-position")
                    and '"migrate":true' in (r.request.post_data or "")
                ):
                    page.goto(base_a + "/code?open=" + quote(str(legacy)))
                assert page.evaluate("window.__aceCurrentIndex") == 2
                page.goto(base_b + "/code?open=" + quote(str(legacy)))
                assert page.evaluate("window.__aceCurrentIndex") == 2

                # Blocking the browser's local mirror must not disable the
                # shared server write or abort the rest of the page script.
                page.add_init_script("""(() => {
                  const original = Storage.prototype.setItem;
                  Storage.prototype.setItem = function (key, value) {
                    if (key.startsWith('ace-source-index:')) {
                      throw new DOMException('blocked', 'QuotaExceededError');
                    }
                    return original.call(this, key, value);
                  };
                })();""")
                page.goto(base_a + "/code?open=" + quote(str(project)))
                with page.expect_response(
                    lambda r: r.url.endswith("/api/navigation")
                    and r.status == 200
                ):
                    page.evaluate("window.aceNavigate(2)")
                page.wait_for_function("window.__aceCurrentIndex === 2")
                page.goto(base_b + "/code?open=" + quote(str(project)))
                assert page.evaluate("window.__aceCurrentIndex") == 2
            finally:
                browser.close()
