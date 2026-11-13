import json
import os
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.services.shared_recent_project import SharedRecentProjectStore


_RUNTIME_ENV = {
    "ACE_LAUNCHER_TOKEN": "test-token",
    "ACE_RUNTIME_FILE": "/tmp/ace-runtime.json",
    "ACE_IDLE_TIMEOUT_SECONDS": "300",
}
_DISABLED_ENV = {
    "ACE_LAUNCHER_TOKEN": "",
    "ACE_RUNTIME_FILE": "",
    "ACE_IDLE_TIMEOUT_SECONDS": "",
}


def _launcher_client():
    app = create_app()
    return TestClient(app), app

def test_full_page_loads_runtime_before_bridge():
    with patch.dict(os.environ, _DISABLED_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get("/")

    runtime_index = resp.text.find('src="/static/js/runtime.js"')
    bridge_index = resp.text.find('src="/static/js/bridge.js"')
    assert resp.status_code == 200
    assert runtime_index != -1
    assert bridge_index != -1
    assert runtime_index < bridge_index


def test_launch_authenticates_and_redirects_to_landing():
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get("/launch?token=test-token", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_launch_authenticates_and_redirects_to_open_project(tmp_path):
    project_path = tmp_path / "project.ace"
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get(
                f"/launch?token=test-token&open={quote(str(project_path))}",
                follow_redirects=False,
            )

    assert resp.status_code == 302
    assert resp.headers["location"] == f"/code?open={quote(str(project_path), safe='')}"


def test_launch_rejects_wrong_token():
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get("/launch?token=wrong", follow_redirects=False)

    assert resp.status_code == 403


def test_heartbeat_records_tab_for_launch_authenticated_session():
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            client.get("/launch?token=test-token", follow_redirects=False)
            resp = client.post("/api/runtime/heartbeat", data={"tab_id": "tab-1"})
            status = client.get("/api/runtime/status")

    assert resp.status_code == 200
    assert resp.json()["active_tabs"] == 1
    assert status.json()["active_tabs"] == 1


def test_disconnect_removes_tab_for_launch_authenticated_session():
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            client.get("/launch?token=test-token", follow_redirects=False)
            client.post("/api/runtime/heartbeat", data={"tab_id": "tab-1"})
            resp = client.post("/api/runtime/disconnect", data={"tab_id": "tab-1"})
            status = client.get("/api/runtime/status")

    assert resp.status_code == 200
    assert resp.json()["active_tabs"] == 0
    assert status.json()["active_tabs"] == 0


def test_status_disabled_in_non_launcher_mode():
    with patch.dict(os.environ, _DISABLED_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            status = client.get("/api/runtime/status")
            heartbeat = client.post("/api/runtime/heartbeat", data={"tab_id": "tab-1"})
            disconnect = client.post("/api/runtime/disconnect", data={"tab_id": "tab-1"})
            quit_resp = client.post("/api/runtime/quit")

    assert status.json() == {"enabled": False, "authenticated": False, "active_tabs": 0}
    assert heartbeat.status_code == 200
    assert heartbeat.json()["enabled"] is False
    assert disconnect.status_code == 200
    assert disconnect.json()["enabled"] is False
    assert quit_resp.status_code == 200
    assert quit_resp.json()["enabled"] is False


def test_status_health_check_accepts_launcher_token_header():
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get(
                "/api/runtime/status",
                headers={"X-ACE-Launcher-Token": "test-token"},
            )

    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert resp.json()["authenticated"] is True


def test_quit_uses_shutdown_callback_for_launch_authenticated_session():
    called = []
    with patch.dict(os.environ, _RUNTIME_ENV, clear=False):
        client, app = _launcher_client()
        with client:
            app.state.browser_runtime_shutdown = lambda: called.append(True)
            client.get("/launch?token=test-token", follow_redirects=False)
            resp = client.post("/api/runtime/quit")

    assert resp.status_code == 200
    assert called == [True]

@pytest.mark.parametrize("runtime_pid", [os.getpid(), 987654321])
def test_lifespan_removes_runtime_file_for_current_token(tmp_path, runtime_pid):
    runtime_file = tmp_path / "runtime.json"
    runtime_file.write_text(
        json.dumps({"pid": runtime_pid, "port": 18080, "token": "test-token"}),
        encoding="utf-8",
    )
    env = {
        "ACE_LAUNCHER_TOKEN": "test-token",
        "ACE_RUNTIME_FILE": str(runtime_file),
        "ACE_IDLE_TIMEOUT_SECONDS": "300",
    }

    with patch.dict(os.environ, env, clear=False):
        client, _app = _launcher_client()
        with client:
            resp = client.get("/api/runtime/status")

    assert resp.status_code == 200
    assert not runtime_file.exists()


def test_lifespan_keeps_newer_runtime_file_with_different_token(tmp_path):
    runtime_file = tmp_path / "runtime.json"
    metadata = {"pid": 987654321, "port": 18081, "token": "newer-token"}
    runtime_file.write_text(json.dumps(metadata), encoding="utf-8")
    env = {
        "ACE_LAUNCHER_TOKEN": "old-token",
        "ACE_RUNTIME_FILE": str(runtime_file),
        "ACE_IDLE_TIMEOUT_SECONDS": "300",
    }

    with patch.dict(os.environ, env, clear=False):
        client, _app = _launcher_client()
        with client:
            assert client.get("/api/runtime/status").status_code == 200

    assert json.loads(runtime_file.read_text(encoding="utf-8")) == metadata


def test_two_runtimes_keep_independent_browser_sessions():
    """Cookies share a host across ports, but launcher authorisation must not."""
    from http.cookiejar import CookieJar

    jar = CookieJar()
    shutdowns = []
    env = {**_RUNTIME_ENV, "ACE_RUNTIME_FILE": ""}
    with patch.dict(os.environ, env, clear=False):
        app_a = create_app()
        app_b = create_app()
        with TestClient(app_a, base_url="http://localhost:18101") as a, TestClient(
            app_b, base_url="http://localhost:18102"
        ) as b:
            app_a.state.browser_runtime_shutdown = lambda: shutdowns.append("a")
            app_b.state.browser_runtime_shutdown = lambda: shutdowns.append("b")
            a.cookies = jar
            b.cookies = jar
            assert a.get("/launch?token=test-token", follow_redirects=False).status_code == 302
            assert a.post("/api/runtime/heartbeat", data={"tab_id": "a"}).status_code == 200
            # The A cookie must never authorise B.
            assert b.post("/api/runtime/heartbeat", data={"tab_id": "b"}).status_code == 403
            assert b.get("/launch?token=test-token", follow_redirects=False).status_code == 302
            assert len(list(jar)) == 2
            assert b.post("/api/runtime/heartbeat", data={"tab_id": "b"}).status_code == 200
            assert a.post("/api/runtime/heartbeat", data={"tab_id": "a"}).status_code == 200
            for client, tab in [(a, "a"), (b, "b")]:
                assert client.get("/api/runtime/status").json()["authenticated"] is True
                assert client.post("/api/runtime/disconnect", data={"tab_id": tab}).status_code == 200
                assert client.post("/api/runtime/quit").status_code == 200
    assert shutdowns == ["a", "b"]


def test_shared_recent_project_is_private_and_survives_runtime_ports(tmp_path):
    env_a = {
        "ACE_LAUNCHER_TOKEN": "token-a",
        "ACE_RUNTIME_FILE": str(tmp_path / "runtime-a.json"),
    }
    env_b = {
        "ACE_LAUNCHER_TOKEN": "token-b",
        "ACE_RUNTIME_FILE": str(tmp_path / "runtime-b.json"),
    }
    with ExitStack() as stack:
        with patch.dict(os.environ, env_a, clear=False):
            a = stack.enter_context(TestClient(
                create_app(), base_url="http://127.0.0.1:18101"
            ))
        with patch.dict(os.environ, env_b, clear=False):
            b = stack.enter_context(TestClient(
                create_app(), base_url="http://127.0.0.1:18102"
            ))
        endpoint = "/api/runtime/recent-project"
        assert a.get(endpoint).status_code == 403
        assert b.post(endpoint, json={"action": "set", "path": "/private.ace"}).status_code == 403
        assert a.get("/launch?token=token-a", follow_redirects=False).status_code == 302
        assert b.get("/launch?token=token-b", follow_redirects=False).status_code == 302

        assert a.post(endpoint, json={
            "action": "migrate", "path": "/old.ace", "opened_at": 123,
        }).json()["recent"] == {"path": "/old.ace", "openedAt": 123}
        assert b.get(endpoint).json()["recent"]["path"] == "/old.ace"
        assert b.post(endpoint, json={
            "action": "set", "path": "/new.ace", "revision": 1,
        }).status_code == 200
        assert a.get(endpoint).json()["recent"]["path"] == "/new.ace"
        assert a.post(endpoint, json={
            "action": "remove", "path": "/old.ace", "revision": 2,
        }).json()[
            "recent"
        ]["path"] == "/new.ace"
        assert b.post(endpoint, json={"action": "clear", "revision": 2}).json()[
            "recent"
        ] is None
        assert a.post(endpoint, json={
            "action": "migrate", "path": "/stale.ace",
        }).json()["recent"] is None
        assert a.post(endpoint, json={
            "action": "set", "path": "", "revision": 3,
        }).status_code == 400

        project = tmp_path / "opened.ace"
        conn = create_project(str(project), "Opened")
        conn.close()
        opened = a.post("/api/project/open", data={"path": str(project)})
        assert opened.headers["HX-Redirect"] == "/import"
        assert b.get(endpoint).json()["recent"]["path"] == str(project)

        created = tmp_path / "created.ace"
        result = b.post("/api/project/create", data={"name": "Created", "path": str(created)})
        assert result.headers["HX-Redirect"] == "/import"
        assert a.get(endpoint).json()["recent"]["path"] == str(created)

        direct = a.get(f"/code?open={quote(str(project), safe='')}")
        assert direct.status_code == 200
        assert b.get(endpoint).json()["recent"]["path"] == str(project)


def test_recent_project_store_keeps_clear_tombstone_across_instances(tmp_path):
    first = SharedRecentProjectStore(tmp_path / "runtime-a.json")
    second = SharedRecentProjectStore(tmp_path / "runtime-b.json")
    first.migrate("/old.ace", opened_at=10)
    assert second.read() == {"path": "/old.ace", "openedAt": 10}
    second.clear()
    first.migrate("/older-port.ace", opened_at=20)
    assert first.read() is None
    first.set("/chosen.ace", opened_at=30)
    assert second.read() == {"path": "/chosen.ace", "openedAt": 30}


def test_stale_retry_cannot_clear_a_newer_project_from_another_port(tmp_path):
    first = SharedRecentProjectStore(tmp_path / "runtime-a.json")
    second = SharedRecentProjectStore(tmp_path / "runtime-b.json")
    first.set("/old.ace")
    stale_revision = first.snapshot()["revision"]
    second.set("/new.ace")
    assert first.clear(expected_revision=stale_revision)["applied"] is False
    assert first.read()["path"] == "/new.ace"
