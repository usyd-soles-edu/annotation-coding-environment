"""Desktop UI preferences render before CSS across different runtime ports."""

import os
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.services.shared_preferences import SharedPreferencesStore


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


def _clients(tmp_path, stack, ports):
    project = tmp_path / "settings.ace"
    conn = create_project(str(project), "Settings")
    add_source(conn, "S1", "One sentence.", "row")
    coder_id = list_coders(conn)[0]["id"]
    conn.close()
    clients = []
    for port, token in ports:
        env = {
            "ACE_LAUNCHER_TOKEN": token,
            "ACE_RUNTIME_FILE": str(tmp_path / f"runtime-{port}.json"),
            "ACE_IDLE_TIMEOUT_SECONDS": "300",
        }
        with patch.dict(os.environ, env, clear=False):
            client = stack.enter_context(TestClient(
                create_app(), base_url=f"http://127.0.0.1:{port}"
            ))
        client.app.state.project_path = str(project)
        client.app.state.coder_id = coder_id
        clients.append(client)
    return clients


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_shared_settings_migrate_render_and_reset_across_ports(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base_a = "http://127.0.0.1:18121"
    base_b = "http://127.0.0.1:18122"
    with ExitStack() as stack:
        a, b = _clients(tmp_path, stack, ((18121, "token-a"), (18122, "token-b")))
        store = SharedPreferencesStore(tmp_path / "runtime-18121.json")
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.route(base_a + "/**", _route_to(a))
                page.route(base_b + "/**", _route_to(b))
                page.goto(base_a + "/launch?token=token-a")
                page.evaluate("""() => {
                  localStorage.setItem('ace-sidebar-width', '384');
                  localStorage.setItem('ace-coding-text-size', '19');
                  localStorage.setItem('ace-grid-collapsed', '1');
                }""")
                page.goto(base_a + "/code")
                page.evaluate("() => window.ACE_PREFS.ready")
                assert store.snapshot()["ace-sidebar-width"]["value"] == "384"
                assert store.snapshot()["ace-coding-text-size"]["value"] == "19"

                page.goto(base_b + "/launch?token=token-b")
                page.goto(base_b + "/code")
                assert page.evaluate("""() => ({
                  width: document.documentElement.style.getPropertyValue('--ace-sidebar-width'),
                  size: document.documentElement.style.getPropertyValue('--ace-coding-text-size'),
                  collapsed: document.documentElement.dataset.aceGridCollapsed
                })""") == {"width": "384px", "size": "19px", "collapsed": "1"}
                page.evaluate("() => window.ACE_PREFS.ready")
                handle = page.get_by_role("separator", name="Resize codebook sidebar")
                handle.focus()
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST"
                    and '"key":"ace-sidebar-width"' in (response.request.post_data or "")
                ):
                    handle.press("ArrowRight")
                page.wait_for_function(
                    "!localStorage.getItem('ace-preference-pending:ace-sidebar-width')"
                )
                assert store.snapshot()["ace-sidebar-width"]["value"] == "408"

                page.goto(base_a + "/code")
                assert page.evaluate(
                    "() => document.documentElement.style.getPropertyValue('--ace-sidebar-width')"
                ) == "408px"
                page.goto(base_b + "/code")
                handle = page.get_by_role("separator", name="Resize codebook sidebar")
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST"
                    and '"key":"ace-sidebar-width"' in (response.request.post_data or "")
                ):
                    handle.dblclick()
                page.wait_for_function(
                    "!localStorage.getItem('ace-preference-pending:ace-sidebar-width')"
                )
                assert store.snapshot()["ace-sidebar-width"]["value"] is None
                page.goto(base_a + "/code")
                assert page.evaluate(
                    "() => document.documentElement.style.getPropertyValue('--ace-sidebar-width')"
                ) == "360px"
                assert page.evaluate(
                    "() => localStorage.getItem('ace-sidebar-width')"
                ) is None
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_stale_preference_retry_does_not_override_newer_port(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base_a = "http://127.0.0.1:18123"
    base_b = "http://127.0.0.1:18124"
    store = SharedPreferencesStore(tmp_path / "runtime-18123.json")
    store.set("ace-sidebar-width", "384", expected_revision=0)
    with ExitStack() as stack:
        a, b = _clients(tmp_path, stack, ((18123, "token-a"), (18124, "token-b")))
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.route(base_a + "/**", _route_to(a))
                page.route(base_b + "/**", _route_to(b))
                page.goto(base_a + "/launch?token=token-a")
                page.goto(base_a + "/code")
                page.evaluate("() => window.ACE_PREFS.ready")

                def fail_width_once(route):
                    if (route.request.method == "POST" and
                            '"key":"ace-sidebar-width"' in (route.request.post_data or "")):
                        route.fulfill(status=503, body="unavailable")
                    else:
                        route.fallback()

                page.route(base_a + "/api/runtime/preferences", fail_width_once, times=1)
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST" and response.status == 503
                ):
                    page.evaluate("() => window.ACE_PREFS.set('ace-sidebar-width', '408')")
                assert store.snapshot()["ace-sidebar-width"]["value"] == "384"
                assert page.evaluate(
                    "() => JSON.parse(localStorage.getItem("
                    "'ace-preference-pending:ace-sidebar-width')).revision"
                ) == 1

                page.goto(base_b + "/launch?token=token-b")
                page.goto(base_b + "/code")
                page.evaluate("() => window.ACE_PREFS.ready")
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST"
                ):
                    page.evaluate("() => window.ACE_PREFS.set('ace-sidebar-width', '440')")
                page.wait_for_function(
                    "!localStorage.getItem('ace-preference-pending:ace-sidebar-width')"
                )
                assert store.snapshot()["ace-sidebar-width"]["value"] == "440"

                page.goto(base_a + "/code")
                page.evaluate("() => window.ACE_PREFS.ready")
                page.wait_for_function(
                    "!localStorage.getItem('ace-preference-pending:ace-sidebar-width')"
                )
                assert store.snapshot()["ace-sidebar-width"]["value"] == "440"
                assert page.evaluate("() => localStorage.getItem('ace-sidebar-width')") == "440"
                page.reload()
                assert page.evaluate(
                    "() => document.documentElement.style.getPropertyValue('--ace-sidebar-width')"
                ) == "440px"
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_non_launcher_note_open_does_not_leave_pending_retry(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "http://127.0.0.1:18125"
    project = tmp_path / "notes.ace"
    conn = create_project(str(project), "Notes")
    add_source(conn, "S1", "One sentence.", "row")
    coder_id = list_coders(conn)[0]["id"]
    conn.close()
    env = {"ACE_LAUNCHER_TOKEN": "", "ACE_RUNTIME_FILE": ""}
    with patch.dict(os.environ, env, clear=False):
        with TestClient(create_app(), base_url=base) as client:
            client.app.state.project_path = str(project)
            client.app.state.coder_id = coder_id
            with sync_api.sync_playwright() as playwright:
                browser = getattr(playwright, engine).launch()
                try:
                    page = browser.new_page()
                    page.route(base + "/**", _route_to(client))
                    page.goto(base + "/code?note=1")
                    page.evaluate("() => window.ACE_PREFS.ready")
                    assert page.evaluate(
                        "() => document.documentElement.dataset.aceNoteOpen"
                    ) == "1"
                    assert page.evaluate(
                        "() => localStorage.getItem('ace-preference-pending:ace-note-open')"
                    ) is None
                    page.evaluate("() => window.aceCloseNote()")
                    assert page.evaluate(
                        "() => localStorage.getItem('ace-note-open')"
                    ) is None
                    page.goto(base + "/code")
                    page.evaluate("() => window.ACE_PREFS.ready")
                    assert page.evaluate(
                        "() => document.documentElement.dataset.aceNoteOpen"
                    ) is None
                finally:
                    browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_new_choice_during_first_migration_is_kept(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "http://127.0.0.1:18126"
    with ExitStack() as stack:
        (client,) = _clients(tmp_path, stack, ((18126, "test-token"),))
        store = SharedPreferencesStore(tmp_path / "runtime-18126.json")
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.route(base + "/**", _route_to(client))
                page.goto(base + "/launch?token=test-token")
                page.evaluate("() => window.ACE_PREFS.ready")
                page.evaluate("() => localStorage.setItem('ace-sidebar-width', '384')")
                page.add_init_script("""(function () {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (url, options) => {
                    const response = originalFetch(url, options);
                    if (url !== '/api/runtime/preferences' ||
                        options?.method !== 'POST' ||
                        JSON.parse(options.body).action !== 'migrate' ||
                        JSON.parse(options.body).key !== 'ace-sidebar-width') {
                      return response;
                    }
                    return response.then(async result => {
                      const body = await result.text();
                      await new Promise(resolve => { window.__releaseMigration = resolve; });
                      return new Response(body, {
                        status: result.status,
                        headers: { 'Content-Type': 'application/json' },
                      });
                    });
                  };
                }());""")
                page.goto(base + "/code")
                page.wait_for_function("typeof window.__releaseMigration === 'function'")
                assert store.snapshot()["ace-sidebar-width"] == {
                    "value": "384", "revision": 1,
                }
                page.evaluate("() => window.ACE_PREFS.set('ace-sidebar-width', '408')")
                page.evaluate("() => window.__releaseMigration()")
                page.wait_for_function(
                    "!localStorage.getItem('ace-preference-pending:ace-sidebar-width')"
                )
                assert store.snapshot()["ace-sidebar-width"]["value"] == "408"
                assert page.evaluate("() => localStorage.getItem('ace-sidebar-width')") == "408"
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_failed_changes_to_different_settings_survive_two_tabs(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "http://127.0.0.1:18127"
    with ExitStack() as stack:
        (client,) = _clients(tmp_path, stack, ((18127, "test-token"),))
        store = SharedPreferencesStore(tmp_path / "runtime-18127.json")
        with sync_api.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            try:
                context = browser.new_context()
                first = context.new_page()
                second = context.new_page()
                for page in (first, second):
                    page.route(base + "/**", _route_to(client))
                first.goto(base + "/launch?token=test-token")
                first.goto(base + "/code")
                first.evaluate("() => window.ACE_PREFS.ready")
                second.goto(base + "/code")
                second.evaluate("() => window.ACE_PREFS.ready")

                def fail_posts(route):
                    if route.request.method == "POST":
                        route.fulfill(status=503, body="unavailable")
                    else:
                        route.fallback()

                for page in (first, second):
                    page.route(base + "/api/runtime/preferences", fail_posts)
                with first.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST" and response.status == 503
                ):
                    first.evaluate("() => window.ACE_PREFS.set('ace-sidebar-width', '384')")
                with second.expect_response(
                    lambda response: response.url.endswith("/api/runtime/preferences")
                    and response.request.method == "POST" and response.status == 503
                ):
                    second.evaluate("() => window.ACE_PREFS.set('ace-coding-text-size', '19')")
                for key in ("ace-sidebar-width", "ace-coding-text-size"):
                    assert first.evaluate(
                        "key => !!localStorage.getItem('ace-preference-pending:' + key)",
                        key,
                    )
                assert store.snapshot() == {}

                for page in (first, second):
                    page.unroute(base + "/api/runtime/preferences", fail_posts)
                first.reload()
                first.evaluate("() => window.ACE_PREFS.ready")
                for key in ("ace-sidebar-width", "ace-coding-text-size"):
                    assert first.evaluate(
                        "key => localStorage.getItem('ace-preference-pending:' + key)",
                        key,
                    ) is None
                assert store.snapshot()["ace-sidebar-width"]["value"] == "384"
                assert store.snapshot()["ace-coding-text-size"]["value"] == "19"
            finally:
                browser.close()
