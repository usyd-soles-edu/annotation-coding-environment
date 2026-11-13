"""Shared source positions are scoped to a project file and coder."""

import os
import shutil
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import checkpoint_and_close, create_project
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.services.shared_source_position import SharedSourcePositionStore, position_key


def test_store_scopes_copies_and_preserves_newer_positions(tmp_path):
    first = tmp_path / "first.ace"
    copy = tmp_path / "copy.ace"
    first.touch()
    shutil.copyfile(first, copy)
    key = position_key(str(first), "same-project-id", "same-coder")
    assert key != position_key(str(copy), "same-project-id", "same-coder")
    assert key != position_key(str(first), "same-project-id", "other-coder")

    store = SharedSourcePositionStore(tmp_path / "runtime.json")
    assert store.read(key) is None
    assert store.set(key, "source-a", migrate=True)["applied"] is True
    assert store.set(key, "source-b")["revision"] == 2
    assert store.set(key, "stale-source", migrate=True) == {
        "applied": False, "source_id": "source-b", "revision": 2,
    }
    assert store.read(key) == {"source_id": "source-b", "revision": 2}
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_authenticated_runtimes_share_only_the_same_project_position(tmp_path):
    project_path = tmp_path / "project.ace"
    copy_path = tmp_path / "copy.ace"
    conn = create_project(str(project_path), "Project")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "A", "First source.", "row")
    add_source(conn, "B", "Second source.", "row")
    checkpoint_and_close(conn)
    shutil.copy2(project_path, copy_path)
    key = position_key(str(project_path), _project_id(project_path), coder_id)

    with ExitStack() as stack:
        clients = []
        for port, token in ((18121, "source-a"), (18122, "source-b")):
            env = {
                "ACE_LAUNCHER_TOKEN": token,
                "ACE_RUNTIME_FILE": str(tmp_path / f"runtime-{port}.json"),
                "ACE_IDLE_TIMEOUT_SECONDS": "300",
            }
            with patch.dict(os.environ, env, clear=False):
                clients.append(stack.enter_context(TestClient(
                    create_app(), base_url=f"http://127.0.0.1:{port}"
                )))

        first, second = clients
        first.get("/launch?token=source-a")
        second.get("/launch?token=source-b")
        first.get("/code", params={"open": str(project_path)})
        second.get("/code", params={"open": str(project_path)})

        # A stale page cannot write into a different project after the runtime
        # changes its active project.
        assert first.post("/api/runtime/source-position", json={
            "project_key": "x" * 64, "source_index": 1,
        }).status_code == 409
        saved = first.post("/api/runtime/source-position", json={
            "project_key": key, "source_index": 1,
        })
        assert saved.status_code == 200
        assert saved.json()["source_id"]
        assert "Second source." in second.get("/code").text
        assert "First source." in second.get("/code?index=0").text

        second.get("/code", params={"open": str(copy_path)})
        assert "First source." in second.get("/code").text
        assert second.post("/api/runtime/source-position", json={
            "project_key": key, "source_index": 1,
        }).status_code == 409

        store = SharedSourcePositionStore(tmp_path / "runtime-18121.json")
        store.set(key, "removed-source")
        assert "First source." in first.get("/code").text
        assert store.read(key)["source_id"] != "removed-source"


def _project_id(path):
    from ace.db.connection import open_project
    from ace.models.project import get_project

    conn = open_project(path)
    try:
        return get_project(conn)["id"]
    finally:
        conn.close()
