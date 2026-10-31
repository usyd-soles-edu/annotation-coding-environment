"""Rendered bootstrap JSON must preserve text without breaking out of script tags."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.fixture(params=["</script>", "</ScRiPt>"])
def unsafe_text(request):
    return request.param + '<script>window.aceJsonProbe = true</script><!-- & \' " café 😀'


@pytest.fixture()
def project_client(tmp_path, unsafe_text):
    app = create_app()
    project = tmp_path / "test.ace"
    conn = create_project(str(project), "JSON safety")
    try:
        coder = list_coders(conn)[0]["id"]
        code = add_code(conn, unsafe_text, "#1565c0", definition=unsafe_text)
        source = add_source(conn, unsafe_text, unsafe_text, "row")
        add_source(conn, "Second", "Another source enables the source grid.", "row")
        add_annotation(conn, source, coder, code, 0, len(unsafe_text), unsafe_text)
    finally:
        conn.close()

    with TestClient(app) as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder
        yield client, code


def _script_json(body, element_id):
    match = re.search(
        rf'<script\b[^>]*\bid="{element_id}"[^>]*>(.*?)</script\s*>',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    assert match, f"Missing JSON script: {element_id}"
    assert "<" not in match.group(1), "JSON must not contain HTML delimiters"
    return json.loads(match.group(1))


def test_coding_bootstrap_json_is_html_safe(project_client, unsafe_text):
    client, _ = project_client
    response = client.get("/code")
    assert response.status_code == 200
    match = re.search(r"window\.__aceCodes = (.*);", response.text)
    assert match, "Missing codebook bootstrap"
    assert "<" not in match.group(1)
    assert json.loads(match.group(1))[0]["name"] == unsafe_text
    sources = _script_json(response.text, "ace-sources-data")
    assert sources[0]["display_id"] == unsafe_text


def test_audit_bootstrap_json_is_html_safe(project_client, unsafe_text):
    client, code = project_client
    response = client.get(f"/code/{code}/view")
    assert response.status_code == 200
    data = _script_json(response.text, "ace-codeview-data")
    assert data["code"]["name"] == unsafe_text
    assert data["code"]["definition"] == unsafe_text
    assert data["sources"][0]["display_id"] == unsafe_text
    assert data["sources"][0]["excerpts"][0]["text"] == unsafe_text


def test_agreement_bootstrap_json_is_html_safe(tmp_path, unsafe_text):
    # Missing paths exercise the error preview without opening real project files.
    paths = [str(tmp_path / f"{unsafe_text}.ace"), str(tmp_path / "missing.ace")]
    with TestClient(create_app()) as client:
        response = client.post("/api/agreement/preview", data={"paths": json.dumps(paths)})
    assert response.status_code == 200
    assert _script_json(response.text, "ace-agreement-selected-paths") == paths
