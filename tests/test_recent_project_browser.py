"""Quick resume follows authenticated desktop runtimes on different ports."""

import os
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.services.shared_recent_project import SharedRecentProjectStore


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


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_quick_resume_migrates_and_shares_across_runtime_ports(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base_a = "http://127.0.0.1:18101"
    base_b = "http://127.0.0.1:18102"
    with ExitStack() as stack:
        clients = []
        for port, token in ((18101, "token-a"), (18102, "token-b")):
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

                page.goto(base_a + "/")
                page.evaluate("""() => localStorage.setItem(
                    'ace-recent-files', JSON.stringify([{path: '/old.ace', openedAt: 123}])
                )""")
                page.reload()
                page.evaluate("() => window.ACE_RECENTS.ready")
                page.get_by_role("link", name="old.ace").wait_for()
                page.goto(base_a + "/launch?token=token-a")
                page.evaluate("() => window.ACE_RECENTS.ready")
                page.get_by_role("link", name="old.ace").wait_for()

                page.goto(base_b + "/")
                assert page.evaluate("() => localStorage.getItem('ace-recent-files')") is None
                page.goto(base_b + "/launch?token=token-b")
                page.evaluate("() => window.ACE_RECENTS.ready")
                page.get_by_role("link", name="old.ace").wait_for()
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/recent-project")
                    and response.request.method == "POST"
                ):
                    page.locator("#resume-clear-btn").click()
                assert page.locator("#resume-link").is_hidden()

                page.goto(base_a + "/")
                page.evaluate("() => window.ACE_RECENTS.ready")
                assert page.locator("#resume-link").is_hidden()
                with page.expect_response(
                    lambda response: response.url.endswith("/api/runtime/recent-project")
                    and response.request.method == "POST"
                ):
                    page.evaluate("() => window.ACE_RECENTS.add('/new.ace')")
                page.goto(base_b + "/")
                page.evaluate("() => window.ACE_RECENTS.ready")
                page.get_by_role("link", name="new.ace").wait_for()
            finally:
                browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_quick_resume_discards_stale_read_and_recovers_after_failures(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "http://127.0.0.1:18103"
    runtime_file = tmp_path / "runtime.json"
    store = SharedRecentProjectStore(runtime_file)
    store.set("/old.ace")
    env = {
        "ACE_LAUNCHER_TOKEN": "test-token",
        "ACE_RUNTIME_FILE": str(runtime_file),
        "ACE_IDLE_TIMEOUT_SECONDS": "300",
    }
    with patch.dict(os.environ, env, clear=False):
        with TestClient(create_app(), base_url=base) as client:
            with sync_api.sync_playwright() as playwright:
                browser = getattr(playwright, engine).launch()
                try:
                    page = browser.new_page()
                    page.route(base + "/**", _route_to(client))
                    page.goto(base + "/launch?token=test-token")
                    page.evaluate("() => window.ACE_RECENTS.ready")
                    page.get_by_role("link", name="old.ace").wait_for()

                    page.evaluate("""() => {
                      const originalFetch = window.fetch.bind(window);
                      window.fetch = (url, options) => {
                        if (url !== '/api/runtime/recent-project' || options?.method) {
                          return originalFetch(url, options);
                        }
                        return originalFetch(url, options).then(async response => {
                          const body = await response.text();
                          await new Promise(resolve => { window.__releaseRecentRead = resolve; });
                          return new Response(body, {
                            status: response.status,
                            headers: { 'Content-Type': 'application/json' },
                          });
                        });
                      };
                      window.__restoreRecentFetch = () => { window.fetch = originalFetch; };
                      window.dispatchEvent(new Event('focus'));
                    }""")
                    page.wait_for_function("typeof window.__releaseRecentRead === 'function'")
                    page.locator("#resume-clear-btn").click()
                    assert page.locator("#resume-link").is_hidden()
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/runtime/recent-project")
                        and response.request.method == "POST"
                        and '"action":"clear"' in (response.request.post_data or "")
                    ):
                        page.evaluate("""() => {
                          window.__restoreRecentFetch();
                          window.__releaseRecentRead();
                        }""")
                    page.wait_for_function("!localStorage.getItem('ace-recent-pending')")
                    assert page.locator("#resume-link").is_hidden()
                    assert store.read() is None

                    fail_post = [True]
                    fail_get = [False]

                    def fail_once(route):
                        request = route.request
                        if (request.method == "POST" and fail_post[0]
                                and '"action":"set"' in (request.post_data or "")):
                            fail_post[0] = False
                            route.fulfill(status=503, body="unavailable")
                        elif request.method == "GET" and fail_get[0]:
                            fail_get[0] = False
                            route.fulfill(status=503, body="unavailable")
                        else:
                            route.fallback()

                    page.route(base + "/api/runtime/recent-project", fail_once)
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/runtime/recent-project")
                        and response.request.method == "POST" and response.status == 503
                    ):
                        page.evaluate("() => window.ACE_RECENTS.add('/retry.ace')")
                    fail_get[0] = True
                    page.reload()
                    page.evaluate("() => window.ACE_RECENTS.ready")
                    page.get_by_role("link", name="retry.ace").wait_for()
                    assert page.evaluate("() => localStorage.getItem('ace-recent-pending')") is None
                    assert store.read()["path"] == "/retry.ace"

                    store.set("/remote.ace")
                    page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                    page.get_by_role("link", name="remote.ace").wait_for()
                finally:
                    browser.close()


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_completed_clear_is_not_replayed_by_another_tab(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "http://127.0.0.1:18104"
    runtime_file = tmp_path / "runtime.json"
    store = SharedRecentProjectStore(runtime_file)
    store.set("/old.ace")
    env = {
        "ACE_LAUNCHER_TOKEN": "test-token",
        "ACE_RUNTIME_FILE": str(runtime_file),
        "ACE_IDLE_TIMEOUT_SECONDS": "300",
    }
    with patch.dict(os.environ, env, clear=False):
        with TestClient(create_app(), base_url=base) as client:
            with sync_api.sync_playwright() as playwright:
                browser = getattr(playwright, engine).launch()
                try:
                    context = browser.new_context()
                    first = context.new_page()
                    second = context.new_page()
                    for page in (first, second):
                        page.route(base + "/**", _route_to(client))
                    first.goto(base + "/launch?token=test-token")
                    first.evaluate("() => window.ACE_RECENTS.ready")
                    first.get_by_role("link", name="old.ace").wait_for()
                    second.goto(base + "/")
                    second.evaluate("() => window.ACE_RECENTS.ready")

                    def fail_first_clear(route):
                        if (route.request.method == "POST" and
                                '"action":"clear"' in (route.request.post_data or "")):
                            route.fulfill(status=503, body="unavailable")
                        else:
                            route.fallback()

                    first.route(base + "/api/runtime/recent-project", fail_first_clear, times=1)
                    with first.expect_response(
                        lambda response: response.url.endswith("/api/runtime/recent-project")
                        and response.request.method == "POST" and response.status == 503
                    ):
                        first.locator("#resume-clear-btn").click()
                    assert store.read()["path"] == "/old.ace"
                    assert first.evaluate(
                        "() => JSON.parse(localStorage.getItem('ace-recent-pending')).action"
                    ) == "clear"

                    second.reload()
                    second.evaluate("() => window.ACE_RECENTS.ready")
                    assert store.read() is None
                    assert second.evaluate(
                        "() => localStorage.getItem('ace-recent-pending')"
                    ) is None
                    with second.expect_response(
                        lambda response: response.url.endswith("/api/runtime/recent-project")
                        and response.request.method == "POST"
                        and '"action":"set"' in (response.request.post_data or "")
                    ):
                        second.evaluate("() => window.ACE_RECENTS.add('/new.ace')")
                    second.wait_for_function("!localStorage.getItem('ace-recent-pending')")
                    assert store.read()["path"] == "/new.ace"

                    first.evaluate("() => window.dispatchEvent(new Event('focus'))")
                    first.get_by_role("link", name="new.ace").wait_for()
                    assert store.read()["path"] == "/new.ace"
                finally:
                    browser.close()
