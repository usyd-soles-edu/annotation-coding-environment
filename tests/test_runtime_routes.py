import json
import os
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient

from ace.app import create_app


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

def test_lifespan_removes_runtime_file_for_current_process(tmp_path):
    runtime_file = tmp_path / "runtime.json"
    runtime_file.write_text(
        json.dumps({"pid": os.getpid(), "port": 18080, "token": "test-token"}),
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
