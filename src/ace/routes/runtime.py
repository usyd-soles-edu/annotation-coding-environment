"""Browser launcher runtime routes."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from ace.services.browser_runtime import BrowserSessionTracker

router = APIRouter()

_SESSION_KEY = "ace_launcher_authenticated"
_TOKEN_HEADER = "X-ACE-Launcher-Token"


def _runtime_tracker(request: Request) -> BrowserSessionTracker | None:
    return getattr(request.app.state, "browser_runtime", None)


def _runtime_enabled(request: Request) -> bool:
    return _runtime_tracker(request) is not None


def _runtime_token(request: Request) -> str:
    tracker = _runtime_tracker(request)
    return tracker.config.token if tracker is not None else ""


def _session_authenticated(request: Request) -> bool:
    return request.session.get(_SESSION_KEY) is True


def _token_authenticated(request: Request, token: str | None = None) -> bool:
    expected = _runtime_token(request)
    if not expected:
        return False
    supplied = token or request.headers.get(_TOKEN_HEADER) or request.query_params.get("token")
    return supplied == expected


def _authenticated(request: Request) -> bool:
    return _session_authenticated(request) or _token_authenticated(request)


def _require_launcher_session(request: Request) -> None:
    if _runtime_enabled(request) and not _session_authenticated(request):
        raise HTTPException(status_code=403)


@router.get("/launch")
async def launch(
    request: Request,
    token: str = Query(...),
    open: str | None = Query(default=None),
):
    if not _runtime_enabled(request) or not _token_authenticated(request, token):
        raise HTTPException(status_code=403)
    request.session[_SESSION_KEY] = True
    if open:
        return RedirectResponse(url=f"/code?open={quote(open, safe='')}", status_code=302)
    return RedirectResponse(url="/", status_code=302)


@router.get("/api/runtime/status")
async def status(request: Request):
    tracker = _runtime_tracker(request)
    authenticated = _authenticated(request) if tracker is not None else False
    return {
        "enabled": tracker is not None,
        "authenticated": authenticated,
        "active_tabs": tracker.active_count() if tracker is not None else 0,
    }


@router.post("/api/runtime/heartbeat")
async def heartbeat(request: Request, tab_id: str = Form(...)):
    tracker = _runtime_tracker(request)
    if tracker is None:
        return {"ok": True, "enabled": False}
    _require_launcher_session(request)
    tracker.heartbeat(tab_id)
    return {"ok": True, "enabled": True, "active_tabs": tracker.active_count()}


@router.post("/api/runtime/disconnect")
async def disconnect(request: Request, tab_id: str = Form(...)):
    tracker = _runtime_tracker(request)
    if tracker is None:
        return {"ok": True, "enabled": False}
    _require_launcher_session(request)
    tracker.disconnect(tab_id)
    return {"ok": True, "enabled": True, "active_tabs": tracker.active_count()}


@router.post("/api/runtime/quit")
async def quit_runtime(request: Request, background_tasks: BackgroundTasks):
    if not _runtime_enabled(request):
        return {"ok": True, "enabled": False}
    _require_launcher_session(request)
    background_tasks.add_task(request.app.state.browser_runtime_shutdown)
    return {"ok": True, "enabled": True}
