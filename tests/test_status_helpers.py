"""Static checks for bridge.js status helpers (Task 2 of notification redesign).

These tests scan the JS source for the expected public API rather than exercising
the IIFE at runtime. Full behavioural verification happens manually in-browser
and via the Playwright pass in Task 8.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

from ace.app import create_app
from ace.routes.api import _require_coder


BRIDGE = Path(__file__).resolve().parent.parent / "src" / "ace" / "static" / "js" / "bridge.js"


def test_bridge_exposes_set_status():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "window._setStatus" in src, "missing _setStatus export"


def test_bridge_has_assertive_announce_branch():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "ace-live-region-assertive" in src, "missing assertive live region handling"


def test_bridge_has_before_swap_4xx_listener():
    """The global htmx:beforeSwap listener must surface 4xx bodies, not drop them."""
    src = BRIDGE.read_text(encoding="utf-8")
    assert "xhr.status < 400" in src, "missing 4xx guard in beforeSwap listener"
    assert "xhr.status >= 500" in src, "missing 5xx exclusion (server tracebacks must not leak)"
    assert "shouldSwap = false" in src, "missing shouldSwap=false on 4xx"


def test_bridge_cheatsheet_lists_v_as_reserved_key():
    src = BRIDGE.read_text(encoding="utf-8")
    assert '1 – 9, 0, a–y (not q v x z n)' in src
    assert '_shortcutRow("V", "View coded text")' in src


def test_require_coder_returns_id_when_set():
    """Happy path: _require_coder returns the id unchanged when set.

    Uses Starlette's documented Request(app=...) form rather than a hand-rolled
    ASGI scope.
    """
    app = create_app()
    app.state.coder_id = "abc-123"
    request = Request({"type": "http", "app": app, "headers": []})
    assert _require_coder(request) == "abc-123"


def test_require_coder_detail_surfaces_in_http_response(tmp_path):
    """End-to-end: an unset coder produces an HTTP 400 whose JSON body carries the human detail.

    The client listener parses the JSON body, so this confirms the detail is
    actually what the browser will see (not just the exception object).
    """
    from ace.db.connection import create_project

    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    conn.close()

    # Project open but coder unset — a coder-gated route should 400.
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = None
        # /code/apply requires a code_id Form param to pass FastAPI body parsing,
        # then reaches _require_coder. Supply a placeholder so we get to the guard.
        resp = client.post("/api/code/apply", data={"code_id": "x"})
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text!r}"
    body = resp.json()
    assert "detail" in body, f"missing detail in 400 body: {body}"
    detail = body["detail"]
    assert detail != "Bad Request"
    assert isinstance(detail, str)
    detail_l = detail.lower()
    assert "coder" in detail_l or "project" in detail_l, (
        f"detail should mention coder/project, got: {detail!r}"
    )
