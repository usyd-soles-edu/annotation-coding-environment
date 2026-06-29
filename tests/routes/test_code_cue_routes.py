"""Tests for the codebook cue API."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation, list_annotations
from ace.models.codebook import add_code
from ace.models.codebook import compute_codebook_hash
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.fixture()
def client_with_cue_project(tmp_path):
    app = create_app()
    db_path = tmp_path / "cues.ace"
    conn = create_project(str(db_path), "Cue Test")
    coder_id = list_coders(conn)[0]["id"]

    add_source(
        conn,
        "S001",
        "I revised my assessment after reading the tutor feedback comments.",
        "row",
    )
    feedback = add_code(
        conn,
        "Feedback uptake",
        "#3366cc",
        definition="Uses feedback comments to revise assessment work.",
    )
    add_code(
        conn,
        "Group logistics",
        "#cc6633",
        definition="Coordinates group meetings, roles, and deadlines.",
    )
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        yield client, feedback


def test_code_cues_endpoint_echoes_identity_and_returns_ranked_cues(
    client_with_cue_project,
):
    client, feedback = client_with_cue_project
    resp = client.post(
        "/api/code-cues",
        json={
            "request_id": 17,
            "current_index": 0,
            "sentence_index": 0,
            "start": 0,
            "end": 67,
            "text": "I revised my assessment after reading the tutor feedback comments.",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["request_id"] == 17
    assert payload["current_index"] == 0
    assert payload["sentence_index"] == 0
    assert payload["start"] == 0
    assert payload["end"] == 67
    assert payload["cues"]
    assert payload["cues"][0]["code_id"] == feedback
    assert payload["cues"][0]["rank"] > 0
    assert "matched_terms" in payload["cues"][0]


def test_code_cues_endpoint_returns_empty_cues_for_stopword_only_text(
    client_with_cue_project,
):
    client, _ = client_with_cue_project
    resp = client.post(
        "/api/code-cues",
        json={
            "request_id": 18,
            "current_index": 0,
            "sentence_index": 0,
            "start": 0,
            "end": 18,
            "text": "the and of to in is",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["request_id"] == 18
    assert payload["cues"] == []


def test_code_cues_endpoint_rejects_malformed_identity(client_with_cue_project):
    client, _ = client_with_cue_project
    resp = client.post(
        "/api/code-cues",
        json={
            "request_id": "not-a-number",
            "current_index": 0,
            "sentence_index": 0,
            "start": 0,
            "end": 18,
            "text": "feedback comments",
        },
    )

    assert resp.status_code == 400


def test_code_cues_endpoint_rejects_non_json_body(client_with_cue_project):
    client, _ = client_with_cue_project
    resp = client.post(
        "/api/code-cues",
        content="not json",
        headers={"content-type": "text/plain"},
    )

    assert resp.status_code == 400


def test_code_cues_endpoint_rejects_non_object_json_body(client_with_cue_project):
    client, _ = client_with_cue_project
    resp = client.post("/api/code-cues", json=["feedback comments"])

    assert resp.status_code == 400


def test_code_cues_endpoint_requires_selected_coder():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/api/code-cues",
            json={"request_id": 1, "text": "feedback comments"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "No coder is selected — open a project from the home page."


def test_code_cues_endpoint_requires_open_project():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.coder_id = "default"
        app.state.project_path = None
        resp = client.post(
            "/api/code-cues",
            json={"request_id": 1, "text": "feedback comments"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "No project is open."


def test_code_cues_endpoint_degrades_to_empty_cues_when_service_fails(
    client_with_cue_project,
    monkeypatch,
):
    client, _ = client_with_cue_project

    import ace.services.code_cues as code_cues

    def no_fts(_conn, _sentence_text, *, limit=3):
        return []

    monkeypatch.setattr(code_cues, "suggest_code_cues", no_fts)

    resp = client.post(
        "/api/code-cues",
        json={
            "request_id": 20,
            "current_index": 0,
            "sentence_index": 0,
            "start": 0,
            "end": 18,
            "text": "feedback comments",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["cues"] == []


def test_code_cues_endpoint_does_not_mutate_project_database(tmp_path):
    app = create_app()
    db_path = tmp_path / "cues.ace"
    conn = create_project(str(db_path), "Cue Test")
    coder_id = list_coders(conn)[0]["id"]
    source_id = add_source(
        conn,
        "S001",
        "I revised my assessment after reading the tutor feedback comments.",
        "row",
    )
    feedback = add_code(
        conn,
        "Feedback uptake",
        "#3366cc",
        definition="Uses feedback comments to revise assessment work.",
    )
    add_annotation(
        conn,
        source_id,
        coder_id,
        feedback,
        2,
        9,
        "revised",
    )
    before_hash = compute_codebook_hash(conn)
    before_annotations = len(list_annotations(conn))
    before_schema = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'trigger', 'view')"
        ).fetchall()
    }
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        resp = client.post(
            "/api/code-cues",
            json={
                "request_id": 19,
                "current_index": 0,
                "sentence_index": 0,
                "start": 0,
                "end": 67,
                "text": "feedback comments helped me revise assessment work",
            },
        )

    assert resp.status_code == 200
    reopened = sqlite3.connect(db_path)
    reopened.row_factory = sqlite3.Row
    try:
        after_schema = {
            row["name"]
            for row in reopened.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'trigger', 'view')"
            ).fetchall()
        }
        assert compute_codebook_hash(reopened) == before_hash
        assert len(list_annotations(reopened)) == before_annotations
        assert after_schema == before_schema
        assert "code_cue_fts" not in after_schema
    finally:
        reopened.close()
