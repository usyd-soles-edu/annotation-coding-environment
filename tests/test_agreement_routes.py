"""Tests for agreement page and API routes."""

import csv
import json
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def client_with_agreement_files(tmp_path):
    """Client fixture with two pre-created .ace files ready for paths-based compute."""
    path_a = _make_ace_file(
        tmp_path / "alice.ace",
        "Project A",
        "Alice",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),
            (1, 0, 0, 8, "Dogs are"),
        ],
    )
    path_b = _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),
            (1, 1, 0, 8, "Dogs are"),
        ],
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, [str(path_a), str(path_b)]


def _make_ace_file(path, project_name, coder_name, sources, codes, annotations):
    """Create a .ace file with sources, codes, and annotations.

    sources: list of (display_id, content_text)
    codes: list of (name, colour)
    annotations: list of (source_index, code_index, start, end, text)
    """
    conn = create_project(str(path), project_name)

    # Rename default coder
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()

    coder_id = conn.execute("SELECT id FROM coder").fetchone()[0]

    source_ids = []
    for display_id, content_text in sources:
        sid = add_source(conn, display_id, content_text, "row")
        source_ids.append(sid)

    code_ids = []
    for name, colour in codes:
        cid = add_code(conn, name, colour)
        code_ids.append(cid)

    for src_idx, code_idx, start, end, text in annotations:
        add_annotation(
            conn,
            source_ids[src_idx],
            coder_id,
            code_ids[code_idx],
            start,
            end,
            text,
        )

    conn.close()
    return path


@pytest.fixture()
def ace_file_a(tmp_path):
    """First .ace file with coder Alice."""
    return _make_ace_file(
        tmp_path / "alice.ace",
        "Project A",
        "Alice",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),  # S1, Positive
            (1, 0, 0, 8, "Dogs are"),  # S2, Positive
        ],
    )


@pytest.fixture()
def ace_file_b(tmp_path):
    """Second .ace file with coder Bob, same sources."""
    return _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),  # S1, Positive (same as Alice)
            (1, 1, 0, 8, "Dogs are"),  # S2, Negative (different from Alice)
        ],
    )


# ── Page renders ──────────────────────────────────────────────────────


def test_agreement_page_renders(client):
    """GET /agreement returns the agreement template."""
    resp = client.get("/agreement")
    assert resp.status_code == 200
    assert "Inter-Coder Agreement" in resp.text
    assert "agreement-results" in resp.text


def test_agreement_picker_clears_cached_results_before_file_selection(client):
    """Picking a new file set must invalidate previous exports even if cancelled."""
    resp = client.get("/agreement")
    assert resp.status_code == 200
    assert 'fetch("/api/agreement/clear"' in resp.text
    assert "clearResponse.ok" in resp.text


def test_agreement_page_reviews_selected_files_before_compute(client):
    """Selected files are previewed and editable before computation starts."""
    resp = client.get("/agreement")

    assert resp.status_code == 200
    assert '"/api/agreement/preview"' in resp.text
    assert "data-agreement-remove" in resp.text
    assert "data-agreement-compute" in resp.text
    assert "_renderAgreementPreview" in resp.text
    assert "_startAgreementCompute" in resp.text


def test_agreement_preview_renders_review_without_computing(client_with_agreement_files):
    client, paths = client_with_agreement_files

    resp = client.post("/api/agreement/preview", data={"paths": json.dumps(paths)})

    assert resp.status_code == 200
    html = resp.text
    assert "Review selected files" in html
    assert "alice.ace" in html
    assert "bob.ace" in html
    assert "2 matched codes" in html
    assert "2 matched sources" in html
    assert "2 sources" in html
    assert "2 total codes" in html
    assert "2 annotations" in html
    assert "data-agreement-compute" in html
    assert 'aria-label="Remove alice.ace"' in html

    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400


def test_agreement_preview_clears_stale_exports(client_with_agreement_files):
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert client.get("/api/agreement/export/results").status_code == 200
    assert client.get("/api/agreement/export/raw").status_code == 200

    resp = client.post("/api/agreement/preview", data={"paths": json.dumps(paths)})

    assert resp.status_code == 200
    assert "Review selected files" in resp.text
    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400


def test_agreement_clear_invalidates_in_flight_compute_worker(
    client, app, ace_file_a, ace_file_b
):
    """A superseded compute worker must not repopulate stale export data."""
    import ace.routes.api as api_mod

    orig_to_thread = api_mod.asyncio.to_thread

    async def stale_to_thread(fn, *args, **kwargs):
        if getattr(fn, "__name__", "") == "_run_agreement":
            api_mod._clear_agreement_cache(app.state)
            return fn(*args, **kwargs)
        return await orig_to_thread(fn, *args, **kwargs)

    api_mod.asyncio.to_thread = stale_to_thread
    try:
        resp = client.post(
            "/api/agreement/compute",
            data={"paths": json.dumps([str(ace_file_a), str(ace_file_b)])},
        )
    finally:
        api_mod.asyncio.to_thread = orig_to_thread

    assert resp.status_code == 204
    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400


def test_agreement_preview_uses_form_paths_contract(client_with_agreement_files):
    client, paths = client_with_agreement_files

    resp = client.post("/api/agreement/preview", json={"paths": paths})

    assert resp.status_code == 200
    assert "Invalid file paths." in resp.text


def test_agreement_preview_hides_full_paths_in_visible_rows(client_with_agreement_files):
    client, paths = client_with_agreement_files

    resp = client.post("/api/agreement/preview", data={"paths": json.dumps(paths)})

    assert resp.status_code == 200
    visible_html = resp.text.split('<script id="ace-agreement-selected-paths"', 1)[0]
    for path in paths:
        assert path not in visible_html
    assert "ace-agreement-selected-paths" in resp.text


def test_agreement_preview_escapes_file_and_coder_text(client, tmp_path):
    path_a = _make_ace_file(
        tmp_path / "alice<&quotable>.ace",
        "Project A",
        "Alice <Lead>",
        sources=[("S1", "Shared text")],
        codes=[("Positive", "#00AA00")],
        annotations=[(0, 0, 0, 6, "Shared")],
    )
    path_b = _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob & Co",
        sources=[("S1", "Shared text")],
        codes=[("Positive", "#00AA00")],
        annotations=[(0, 0, 0, 6, "Shared")],
    )

    resp = client.post(
        "/api/agreement/preview",
        data={"paths": json.dumps([str(path_a), str(path_b)])},
    )

    assert resp.status_code == 200
    visible_html = resp.text.split('<script id="ace-agreement-selected-paths"', 1)[0]
    assert "Alice &lt;Lead&gt;" in visible_html
    assert "Bob &amp; Co" in visible_html
    assert "alice&lt;&amp;quotable&gt;.ace" in visible_html
    assert "Alice <Lead>" not in visible_html
    assert "Bob & Co" not in visible_html


def test_agreement_preview_disables_compute_for_unmatched_set(client, tmp_path):
    path_a = _make_ace_file(
        tmp_path / "alice.ace",
        "Project A",
        "Alice",
        sources=[("S1", "Alpha only")],
        codes=[("Positive", "#00AA00")],
        annotations=[(0, 0, 0, 5, "Alpha")],
    )
    path_b = _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob",
        sources=[("S2", "Beta only")],
        codes=[("Positive", "#00AA00")],
        annotations=[(0, 0, 0, 4, "Beta")],
    )

    resp = client.post(
        "/api/agreement/preview",
        data={"paths": json.dumps([str(path_a), str(path_b)])},
    )

    assert resp.status_code == 200
    assert "These files share no source texts" in resp.text
    assert "data-agreement-compute" in resp.text
    assert "disabled" in resp.text


def test_agreement_preview_shows_bad_file_error_and_disables_compute(
    client, ace_file_a, tmp_path
):
    bad_path = tmp_path / "not-ace.txt"
    bad_path.write_text("not a sqlite database", encoding="utf-8")

    resp = client.post(
        "/api/agreement/preview",
        data={"paths": json.dumps([str(ace_file_a), str(bad_path)])},
    )

    assert resp.status_code == 200
    assert "alice.ace" in resp.text
    assert "not-ace.txt" in resp.text
    assert "disabled" in resp.text


# ── Compute ───────────────────────────────────────────────────────────


def test_compute(client, ace_file_a, ace_file_b):
    """Compute with paths param returns metrics results."""
    paths = json.dumps([str(ace_file_a), str(ace_file_b)])
    resp = client.post("/api/agreement/compute", data={"paths": paths})
    assert resp.status_code == 200
    assert "Krippendorff" in resp.text
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    assert "Overall (pooled)" in resp.text


def test_compute_returns_new_results_html(client_with_agreement_files):
    """Compute returns new minimalist results: title bar, context, table, references."""
    client, paths = client_with_agreement_files
    resp = client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert resp.status_code == 200
    html = resp.text
    assert "ace-agreement-title-bar" in html
    assert "Summary CSV" in html
    assert "Raw data CSV" in html
    assert "ace-agreement-context" in html
    assert "Overall (pooled)" in html
    assert "ace-agreement-table" in html
    assert "ace-refs" in html
    assert "Krippendorff" in html
    # Smoke tests for new elements
    assert "ace-verdict" in html
    assert "ace-status" in html
    assert "Table 1:" in html
    assert "ace-section-heading" in html


def test_compute_insufficient_files(client, ace_file_a):
    """Computing with < 2 paths returns error HTML (returns 200 so HTMX swaps it in)."""
    paths = json.dumps([str(ace_file_a)])
    resp = client.post("/api/agreement/compute", data={"paths": paths})
    assert resp.status_code == 200
    assert "at least" in resp.text.lower()
    # Error fragment must include the Choose different files button
    assert "Choose different files" in resp.text


# ── Progress endpoint ─────────────────────────────────────────────────


def test_agreement_progress_default_shape(client):
    """GET /api/agreement/progress returns the expected shape with sensible defaults."""
    resp = client.get("/api/agreement/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"percent", "stage", "done", "error"}
    assert isinstance(data["percent"], int)
    assert 0 <= data["percent"] <= 100
    assert isinstance(data["stage"], str)
    assert isinstance(data["done"], bool)
    # error is null or str
    assert data["error"] is None or isinstance(data["error"], str)


def test_agreement_progress_reflects_state(client, app):
    """Progress endpoint reads app.state.agreement_progress when set."""
    app.state.agreement_progress = {
        "percent": 42,
        "stage": "Computing agreement",
        "done": False,
        "error": None,
    }
    resp = client.get("/api/agreement/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert data["percent"] == 42
    assert data["stage"] == "Computing agreement"
    assert data["done"] is False
    assert data["error"] is None


def test_agreement_progress_error_variant(client, app):
    """Progress endpoint surfaces the error field."""
    app.state.agreement_progress = {
        "percent": 0,
        "stage": "",
        "done": False,
        "error": "No shared sources",
    }
    resp = client.get("/api/agreement/progress")
    data = resp.json()
    assert data["error"] == "No shared sources"
    assert data["done"] is False


def test_compute_sets_progress_done_on_success(client, ace_file_a, ace_file_b):
    """A successful compute leaves progress marked done at 100%."""
    paths = json.dumps([str(ace_file_a), str(ace_file_b)])
    resp = client.post("/api/agreement/compute", data={"paths": paths})
    assert resp.status_code == 200
    prog = client.get("/api/agreement/progress").json()
    assert prog["done"] is True
    assert prog["percent"] == 100
    assert prog["error"] is None


def test_compute_error_sets_progress_error(client, ace_file_a):
    """A failed compute (insufficient files) leaves no error in progress (rejected early)."""
    paths = json.dumps([str(ace_file_a)])
    client.post("/api/agreement/compute", data={"paths": paths})
    # Invalid input rejected before the thread runs — progress stays whatever it was.
    resp = client.get("/api/agreement/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"percent", "stage", "done", "error"}


def test_compute_exception_yields_error_state_not_500(client, ace_file_a, ace_file_b, app):
    """An exception inside compute_agreement is caught by the worker catch-all:
    the route returns 200 with an error fragment and agreement_progress["error"]
    is set — never a 500 that leaves the poll bar spinning forever."""
    import ace.routes.api as api_mod
    import ace.services.agreement_computer as computer_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic compute failure")

    orig = computer_mod.compute_agreement
    # The route imports compute_agreement locally, so patch the source module.
    computer_mod.compute_agreement = _boom
    try:
        paths = json.dumps([str(ace_file_a), str(ace_file_b)])
        resp = client.post("/api/agreement/compute", data={"paths": paths})
    finally:
        computer_mod.compute_agreement = orig

    assert resp.status_code == 200, "expected 200 with error fragment, got 500"
    assert "Choose different files" in resp.text
    prog = client.get("/api/agreement/progress").json()
    assert prog["error"], "agreement_progress['error'] should be set on failure"
    assert prog["done"] is False


def test_compute_runs_off_thread(client, ace_file_a, ace_file_b, app):
    """Compute runs in a worker thread (asyncio.to_thread), not on the event loop.

    We instrument asyncio.to_thread so that when it is asked to run the agreement
    worker, it records the call. If the route runs compute synchronously on the
    event loop instead, the instrumented to_thread is never invoked and the test
    fails.
    """
    import asyncio

    real_to_thread = asyncio.to_thread
    calls = []

    async def spy_to_thread(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real_to_thread(fn, *args, **kwargs)

    # Patch the asyncio.to_thread name looked up by the route module.
    import ace.routes.api as api_mod

    orig = api_mod.asyncio.to_thread
    api_mod.asyncio.to_thread = spy_to_thread
    try:
        paths = json.dumps([str(ace_file_a), str(ace_file_b)])
        resp = client.post("/api/agreement/compute", data={"paths": paths})
        assert resp.status_code == 200
    finally:
        api_mod.asyncio.to_thread = orig

    # The route must have delegated to a worker via to_thread.
    assert any(name == "_run_agreement" for name in calls), (
        f"agreement_compute did not offload to a thread (to_thread calls: {calls})"
    )


def test_compute_missing_paths(client):
    """Computing with no paths param returns an HTMX-swappable error fragment."""
    resp = client.post("/api/agreement/compute")
    assert resp.status_code == 200
    assert "Invalid file paths." in resp.text


# ── Export ────────────────────────────────────────────────────────────


def test_export_csv(client, ace_file_a, ace_file_b):
    """Export returns CSV with per-code metrics after compute."""
    paths = json.dumps([str(ace_file_a), str(ace_file_b)])
    client.post("/api/agreement/compute", data={"paths": paths})

    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/csv")
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    assert "percent_agreement" in resp.text


def test_export_summary_csv_has_metadata_and_overall(client_with_agreement_files):
    """Summary CSV includes metadata columns, n_sources column, and Overall row."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    reader = csv.DictReader(StringIO(resp.text))
    rows = list(reader)
    assert reader.fieldnames[:4] == ["export_date", "files", "coders", "code"]
    assert "n_sources" in reader.fieldnames
    assert any(row["code"] == "Overall" for row in rows)


def test_export_raw_data_csv(client_with_agreement_files):
    """Raw data CSV has correct columns and content-type."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    resp = client.get("/api/agreement/export/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    reader = csv.DictReader(StringIO(resp.text))
    rows = list(reader)
    assert reader.fieldnames == [
        "export_date",
        "coders",
        "n_sources",
        "n_codes",
        "source_id",
        "start_offset",
        "end_offset",
        "coder_id",
        "code_name",
    ]
    assert rows


def test_clear_agreement_cache_invalidates_cached_exports(client_with_agreement_files):
    """Clear endpoint removes old computed data before choosing a replacement set."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert client.get("/api/agreement/export/results").status_code == 200
    assert client.get("/api/agreement/export/raw").status_code == 200

    resp = client.post("/api/agreement/clear")
    assert resp.status_code == 204

    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400


def test_failed_agreement_compute_invalidates_cached_exports(client_with_agreement_files):
    """A failed replacement compute must not leave previous exports live."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert client.get("/api/agreement/export/results").status_code == 200
    assert client.get("/api/agreement/export/raw").status_code == 200

    resp = client.post("/api/agreement/compute", data={"paths": json.dumps(paths[:1])})
    assert resp.status_code == 200
    assert "Select at least 2" in resp.text

    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400


def test_missing_paths_compute_invalidates_cached_exports(client_with_agreement_files):
    """Missing form data must still clear old agreement exports."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert client.get("/api/agreement/export/results").status_code == 200
    assert client.get("/api/agreement/export/raw").status_code == 200

    resp = client.post("/api/agreement/compute")
    assert resp.status_code == 200
    assert "Invalid file paths." in resp.text

    assert client.get("/api/agreement/export/results").status_code == 400
    assert client.get("/api/agreement/export/raw").status_code == 400
