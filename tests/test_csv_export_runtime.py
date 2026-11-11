"""CSV downloads keep the event loop responsive and clean temporary files."""

import asyncio
import csv
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from starlette.requests import Request

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.routes import api_support


def _project(tmp_path):
    app = create_app()
    path = tmp_path / "export.ace"
    conn = create_project(str(path), "Export test")
    coder_id = list_coders(conn)[0]["id"]
    conn.close()
    return app, path, coder_id


def _capture_temp_files(monkeypatch, tmp_path):
    original = api_support.tempfile.NamedTemporaryFile
    paths = []

    def capture(*args, **kwargs):
        kwargs["dir"] = tmp_path
        file = original(*args, **kwargs)
        paths.append(Path(file.name))
        return file

    monkeypatch.setattr(api_support.tempfile, "NamedTemporaryFile", capture)
    return paths


def test_export_worker_keeps_other_requests_responsive(tmp_path, monkeypatch):
    from ace.services import exporter

    app, path, coder_id = _project(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    worker_thread = []

    def slow_writer(conn, output_path, merge_adjacent=False):
        worker_thread.append(threading.get_ident())
        assert conn.execute("SELECT 1").fetchone()[0] == 1
        entered.set()
        assert release.wait(10)
        Path(output_path).write_text("source_id\n", encoding="utf-8")

    monkeypatch.setattr(exporter, "export_annotations_csv", slow_writer)
    with TestClient(app) as client:
        app.state.project_path = str(path)
        app.state.coder_id = coder_id
        with ThreadPoolExecutor(max_workers=1) as pool:
            download = pool.submit(client.get, "/api/export/annotations")
            try:
                assert entered.wait(5)
                start = time.monotonic()
                heartbeat = client.get("/api/runtime/status")
                elapsed = time.monotonic() - start
                assert heartbeat.status_code == 200
                assert elapsed < 1.0
            finally:
                release.set()
            assert download.result(timeout=10).status_code == 200
    assert worker_thread[0] != threading.get_ident()


def test_export_cleans_temp_file_when_writer_fails(tmp_path, monkeypatch):
    from ace.services import exporter

    app, path, coder_id = _project(tmp_path)
    paths = _capture_temp_files(monkeypatch, tmp_path)

    def failing_writer(conn, output_path, merge_adjacent=False):
        Path(output_path).write_text("partial", encoding="utf-8")
        raise RuntimeError("writer failed")

    monkeypatch.setattr(exporter, "export_annotations_csv", failing_writer)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(path)
        app.state.coder_id = coder_id
        assert client.get("/api/export/annotations").status_code == 500
    assert paths and all(not path.exists() for path in paths)


def test_export_cleans_temp_file_when_send_fails(tmp_path):
    path = tmp_path / "prepared.csv"
    path.write_text("header\n", encoding="utf-8")
    response = api_support._TemporaryCsvResponse(path, media_type="text/csv")

    async def send(message):
        if message["type"] == "http.response.body":
            raise RuntimeError("client disconnected")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "headers": [], "http_version": "1.1"}
    with pytest.raises(RuntimeError, match="client disconnected"):
        asyncio.run(response(scope, receive, send))
    assert not path.exists()


def test_export_cleans_temp_file_when_preparation_is_cancelled(tmp_path, monkeypatch):
    app, path, _coder_id = _project(tmp_path)
    app.state.project_path = str(path)
    paths = _capture_temp_files(monkeypatch, tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_writer(conn, output_path):
        entered.set()
        assert release.wait(5)
        Path(output_path).write_text("source_id\n", encoding="utf-8")
        finished.set()

    async def run():
        request = Request({"type": "http", "app": app})
        task = asyncio.create_task(api_support._csv_download(request, "annotations", slow_writer))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(finished.wait, 2)
        for _ in range(50):
            if all(not path.exists() for path in paths):
                break
            await asyncio.sleep(0.01)

    asyncio.run(run())
    assert paths and all(not path.exists() for path in paths)


def test_export_cleans_temp_file_when_event_loop_shuts_down(tmp_path, monkeypatch):
    app, path, _coder_id = _project(tmp_path)
    app.state.project_path = str(path)
    paths = _capture_temp_files(monkeypatch, tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_writer(conn, output_path):
        entered.set()
        assert release.wait(5)
        Path(output_path).write_text("source_id\n", encoding="utf-8")
        finished.set()

    async def run():
        request = Request({"type": "http", "app": app})
        task = asyncio.create_task(api_support._csv_download(request, "annotations", slow_writer))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # asyncio.run now cancels the in-flight to_thread task during shutdown.
        # Release the real worker only after that cancellation has started.
        timer = threading.Timer(0.1, release.set)
        timer.start()
        return timer

    timer = asyncio.run(run())
    timer.join(timeout=2)
    assert finished.wait(2)
    assert paths and all(not path.exists() for path in paths)


def test_annotation_export_uses_one_snapshot_for_metadata_and_rows(tmp_path, monkeypatch):
    from ace.services import exporter

    path = tmp_path / "snapshot.ace"
    conn = create_project(str(path), "Snapshot")
    coder_id = list_coders(conn)[0]["id"]
    code_id = add_code(conn, "Theme", "#AA0000")
    source_id = add_source(conn, "S1", "A B", "row", metadata={"base": "old"})
    add_annotation(conn, source_id, coder_id, code_id, 0, 1, "A")
    conn.close()

    discovered = threading.Event()
    release = threading.Event()
    original_fieldname = exporter._metadata_fieldname

    def pause_after_discovery(*args):
        discovered.set()
        assert release.wait(5)
        return original_fieldname(*args)

    monkeypatch.setattr(exporter, "_metadata_fieldname", pause_after_discovery)
    output = tmp_path / "snapshot.csv"

    def export():
        reader = sqlite3.connect(path)
        reader.row_factory = sqlite3.Row
        reader.execute("PRAGMA journal_mode = WAL")
        try:
            return exporter.export_annotations_csv(reader, output)
        finally:
            reader.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(export)
        try:
            assert discovered.wait(2)
            writer = sqlite3.connect(path)
            writer.row_factory = sqlite3.Row
            try:
                new_source = add_source(
                    writer, "S2", "C D", "row", metadata={"new_column": "new"}
                )
                add_annotation(writer, new_source, coder_id, code_id, 0, 1, "C")
            finally:
                writer.close()
        finally:
            release.set()
        assert result.result(timeout=5) == 1

    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["base"] == "old"
    assert "new_column" not in rows[0]
