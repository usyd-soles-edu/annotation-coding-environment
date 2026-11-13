"""Browser launcher runtime routes."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote
import sqlite3

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ace.services.browser_runtime import BrowserSessionTracker
from ace.services.shared_recent_project import SharedRecentProjectStore

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


class RecentProjectChange(BaseModel):
    action: Literal["set", "migrate", "remove", "clear"]
    path: str = Field(default="", max_length=32768)
    opened_at: int = Field(default=0, ge=0, le=2**63 - 1)
    revision: int | None = Field(default=None, ge=0)


def _recent_store(request: Request) -> SharedRecentProjectStore | None:
    _require_launcher_session(request)
    return getattr(request.app.state, "shared_recent_project_store", None)


@router.get("/api/runtime/recent-project")
def recent_project(request: Request):
    store = _recent_store(request)
    if store is None:
        return {"enabled": False, "recent": None}
    try:
        return {"enabled": True, **store.snapshot()}
    except (OSError, sqlite3.Error):
        raise HTTPException(status_code=503, detail="Recent project history unavailable") from None


@router.post("/api/runtime/recent-project")
def change_recent_project(request: Request, change: RecentProjectChange):
    store = _recent_store(request)
    if store is None:
        return {"enabled": False, "recent": None}
    try:
        if change.action != "migrate" and change.revision is None:
            raise HTTPException(status_code=422, detail="Recent project revision required")
        if change.action == "set":
            result = store.set(change.path, expected_revision=change.revision)
        elif change.action == "migrate":
            result = store.migrate(change.path, opened_at=change.opened_at)
        elif change.action == "remove":
            if not change.path:
                raise ValueError("Invalid recent project path")
            result = store.clear(if_path=change.path, expected_revision=change.revision)
        else:
            result = store.clear(expected_revision=change.revision)
        return {"enabled": True, **result}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recent project path") from None
    except (OSError, sqlite3.Error):
        raise HTTPException(status_code=503, detail="Recent project history unavailable") from None


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
