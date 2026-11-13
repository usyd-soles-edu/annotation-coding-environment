"""UI preferences survive desktop port changes without stale retries winning."""

import os
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

from ace.app import create_app
from ace.services.shared_preferences import SharedPreferencesStore


def test_preference_store_migration_tombstones_and_per_key_revisions(tmp_path):
    first = SharedPreferencesStore(tmp_path / "runtime-a.json")
    second = SharedPreferencesStore(tmp_path / "runtime-b.json")
    assert first.snapshot() == {}
    assert first.migrate("ace-sidebar-width", "384")["entry"] == {
        "value": "384", "revision": 1,
    }
    assert second.migrate("ace-sidebar-width", "400")["applied"] is False
    assert second.snapshot()["ace-sidebar-width"]["value"] == "384"

    assert first.set("ace-sidebar-width", None, expected_revision=1)["applied"]
    assert second.migrate("ace-sidebar-width", "400")["applied"] is False
    assert second.snapshot()["ace-sidebar-width"] == {
        "value": None, "revision": 2,
    }
    assert first.set("ace-grid-height", "20.00vh", expected_revision=0)["applied"]
    assert second.set("ace-sidebar-width", "408", expected_revision=2)["applied"]
    assert first.set("ace-sidebar-width", "360", expected_revision=1)["applied"] is False
    assert second.snapshot()["ace-sidebar-width"]["value"] == "408"
    assert second.snapshot()["ace-grid-height"]["value"] == "20.00vh"


def test_preference_routes_are_private_and_shared_between_runtime_ports(tmp_path):
    clients = []
    with ExitStack() as stack:
        for port, token in ((18111, "token-a"), (18112, "token-b")):
            env = {
                "ACE_LAUNCHER_TOKEN": token,
                "ACE_RUNTIME_FILE": str(tmp_path / f"runtime-{port}.json"),
                "ACE_IDLE_TIMEOUT_SECONDS": "300",
            }
            with patch.dict(os.environ, env, clear=False):
                clients.append(stack.enter_context(TestClient(
                    create_app(), base_url=f"http://127.0.0.1:{port}"
                )))
        a, b = clients
        endpoint = "/api/runtime/preferences"
        assert a.get(endpoint).status_code == 403
        assert b.post(endpoint, json={
            "action": "set", "key": "ace-sidebar-width", "value": "384",
            "revision": 0,
        }).status_code == 403
        a.get("/launch?token=token-a")
        b.get("/launch?token=token-b")

        migrated = a.post(endpoint, json={
            "action": "migrate", "key": "ace-sidebar-width", "value": "384",
        }).json()
        assert migrated["applied"] is True
        assert migrated["entry"] == {"value": "384", "revision": 1}
        assert b.get(endpoint).json()["preferences"]["ace-sidebar-width"] == migrated["entry"]

        newer = b.post(endpoint, json={
            "action": "set", "key": "ace-sidebar-width", "value": "408",
            "revision": 1,
        }).json()
        assert newer["applied"] is True
        stale = a.post(endpoint, json={
            "action": "set", "key": "ace-sidebar-width", "value": None,
            "revision": 1,
        }).json()
        assert stale["applied"] is False
        assert stale["entry"] == {"value": "408", "revision": 2}

        assert a.post(endpoint, json={
            "action": "set", "key": "ace-sidebar-width", "value": "10001",
            "revision": 2,
        }).status_code == 400
        assert a.post(endpoint, json={
            "action": "set", "key": "ace-unknown", "value": "1",
            "revision": 0,
        }).status_code == 400
        assert a.post(endpoint, json={
            "action": "set", "key": "ace-grid-height", "value": "20vh",
        }).status_code == 422
