"""FastAPI application factory for ACE."""

import json
import os
import secrets
import signal
import sqlite3
import subprocess
import threading
import time
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks
from starlette.middleware.sessions import SessionMiddleware

from ace.db.connection import checkpoint_and_close
from ace.db.schema import ACE_APPLICATION_ID
from ace.services.browser_runtime import (
    BrowserRuntimeConfig,
    BrowserRuntimeMonitor,
    BrowserSessionTracker,
)

_DATA_DIR = Path.home() / ".ace"
_PKG_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# HtmxRedirect — raised inside get_db or routes to redirect via HTMX
# ---------------------------------------------------------------------------


class HtmxRedirect(Exception):
    """Raise to redirect the client (works for both HTMX and plain requests)."""

    def __init__(self, url: str) -> None:
        self.url = url


def _htmx_redirect_handler(request: Request, exc: HtmxRedirect) -> Response:
    """Return an HX-Redirect header for HTMX requests, else a 302."""
    if request.headers.get("HX-Request"):
        return Response(
            status_code=200,
            headers={"HX-Redirect": exc.url},
        )
    return Response(
        status_code=302,
        headers={"Location": exc.url},
    )


# ---------------------------------------------------------------------------
# CSRF middleware
# ---------------------------------------------------------------------------

_ALLOWED_ORIGINS: frozenset[str] | None = None


def _build_allowed_origins(port: int) -> frozenset[str]:
    return frozenset(
        f"{scheme}://{host}:{port}"
        for scheme in ("http",)
        for host in ("127.0.0.1", "localhost")
    )


class _CSRFMiddleware:
    """Reject mutating requests whose Origin header doesn't match localhost."""

    _SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method not in self._SAFE_METHODS:
            origin = request.headers.get("origin")
            allowed = _ALLOWED_ORIGINS or _build_allowed_origins(
                int(scope.get("server", ("", 8080))[1])
            )
            if origin is not None and origin not in allowed:
                response = Response("CSRF origin rejected", status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# get_db dependency
# ---------------------------------------------------------------------------


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """Open a per-request SQLite connection for the current project.

    Validates that the project path exists and has the correct application_id.
    Enables foreign keys and WAL mode. Closes the connection when the request
    is done.

    Raises HtmxRedirect("/") if no project is set, the path doesn't exist,
    or the file is not a valid ACE database.
    """
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None:
        raise HtmxRedirect("/")

    path = Path(project_path)
    if not path.exists():
        raise HtmxRedirect("/")

    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        app_id = conn.execute("PRAGMA application_id").fetchone()[0]
        if app_id != ACE_APPLICATION_ID:
            raise HtmxRedirect("/")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------



def _runtime_config_from_env() -> BrowserRuntimeConfig:
    token = os.environ.get("ACE_LAUNCHER_TOKEN", "")
    runtime_file = os.environ.get("ACE_RUNTIME_FILE")
    idle_timeout = os.environ.get("ACE_IDLE_TIMEOUT_SECONDS")
    return BrowserRuntimeConfig(
        enabled=bool(token),
        token=token,
        runtime_file=Path(runtime_file) if runtime_file else None,
        idle_timeout_seconds=float(idle_timeout) if idle_timeout else 300.0,
    )


def _sigterm_handler(signum, frame):
    raise KeyboardInterrupt


def _install_sigterm_handler() -> None:
    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except ValueError:
        # Signal handlers can only be installed from the main thread. Tests may
        # exercise lifespan from a worker thread; packaged ACE runs on main.
        pass


def _request_process_shutdown() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


def _remove_runtime_file_for_current_process(config: BrowserRuntimeConfig) -> None:
    if config.runtime_file is None:
        return
    try:
        data = json.loads(config.runtime_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.get("pid") != os.getpid():
        return
    try:
        config.runtime_file.unlink()
    except FileNotFoundError:
        pass

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    runtime_shutdown = getattr(
        app.state,
        "browser_runtime_shutdown",
        _request_process_shutdown,
    )
    _DATA_DIR.mkdir(exist_ok=True)
    app.state.db = None
    app.state.project_path = None
    app.state.undo_managers = {}
    app.state.migrated_paths = set()
    app.state.active_projects = set()
    app.state.browser_runtime_config = _runtime_config_from_env()
    app.state.browser_runtime = None
    app.state.browser_runtime_monitor = None
    app.state.browser_runtime_shutdown = runtime_shutdown
    if app.state.browser_runtime_config.enabled:
        _install_sigterm_handler()
        tracker = BrowserSessionTracker(app.state.browser_runtime_config)
        app.state.browser_runtime = tracker
        monitor = BrowserRuntimeMonitor(
            tracker,
            lambda: app.state.browser_runtime_shutdown(),
        )
        app.state.browser_runtime_monitor = monitor
        monitor.start()
    try:
        yield
    finally:
        monitor: BrowserRuntimeMonitor | None = getattr(
            app.state,
            "browser_runtime_monitor",
            None,
        )
        if monitor is not None:
            monitor.stop()
            app.state.browser_runtime_monitor = None
        conn: sqlite3.Connection | None = getattr(app.state, "db", None)
        if conn is not None:
            checkpoint_and_close(conn)
            app.state.db = None
        _remove_runtime_file_for_current_process(app.state.browser_runtime_config)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(lifespan=_lifespan)

    # Exception handlers
    app.add_exception_handler(HtmxRedirect, _htmx_redirect_handler)

    # Middleware (applied bottom-up: CSRF runs first, then session)
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
    app.add_middleware(_CSRFMiddleware)

    # Static files
    app.mount("/static", StaticFiles(directory=str(_PKG_DIR / "static")), name="static")

    # Templates
    app.state.templates = Jinja2Blocks(directory=str(_PKG_DIR / "templates"))
    from markupsafe import Markup
    app.state.templates.env.filters["tojson"] = lambda v: Markup(json.dumps(v))

    # Routes
    from ace.routes.api import router as api_router
    from ace.routes.pages import router as pages_router
    from ace.routes.runtime import router as runtime_router

    app.include_router(runtime_router)
    app.include_router(pages_router)
    app.include_router(api_router)

    return app


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------


def _kill_stale_server(port: int) -> None:
    """Kill any existing process on the given port so we can bind cleanly."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().splitlines()
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        time.sleep(0.5)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


def _kill_stale_ace_instances() -> None:
    """Kill any other ACE server processes regardless of port.

    Single-user local app — one ACE at a time. Prevents confusion from
    browser tabs pointing at leftover dev servers on other ports.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ace.app:create_app"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        me = os.getpid()
        killed = False
        for raw in result.stdout.split():
            try:
                pid = int(raw)
            except ValueError:
                continue
            if pid == me:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except ProcessLookupError:
                pass
        if killed:
            time.sleep(0.5)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass


def _start_parent_watchdog(
    parent_pid: int,
    shutdown: Callable[[], None] = _request_process_shutdown,
) -> None:
    """Terminate the sidecar if its parent launcher process disappears."""
    if parent_pid <= 1:
        return

    def _watch_parent() -> None:
        while True:
            time.sleep(1)
            if not _parent_pid_exists(parent_pid):
                shutdown()
                return

    threading.Thread(target=_watch_parent, daemon=True).start()


def _parent_pid_exists(parent_pid: int) -> bool:
    try:
        os.kill(parent_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run(
    port: int | None = None,
    parent_pid: int | None = None,
    *,
    launcher_token: str | None = None,
    runtime_file: str | None = None,
    idle_timeout_seconds: float | None = None,
    kill_stale: bool = True,
) -> None:
    if port is None:
        port = int(os.environ.get("ACE_PORT", "8080"))
    if launcher_token:
        os.environ["ACE_LAUNCHER_TOKEN"] = launcher_token
    if runtime_file:
        os.environ["ACE_RUNTIME_FILE"] = runtime_file
    if idle_timeout_seconds is not None:
        os.environ["ACE_IDLE_TIMEOUT_SECONDS"] = str(idle_timeout_seconds)
    global _ALLOWED_ORIGINS
    _ALLOWED_ORIGINS = _build_allowed_origins(port)
    if kill_stale:
        _kill_stale_ace_instances()
        _kill_stale_server(port)
    # Nuitka's onefile bootloader may not forward SIGTERM to the Python
    # process cleanly. Explicitly convert SIGTERM to KeyboardInterrupt so
    # uvicorn runs its graceful shutdown path (close connections, run
    # lifespan shutdown, release the SQLite database).
    _install_sigterm_handler()
    server: uvicorn.Server

    def _request_server_shutdown() -> None:
        server.should_exit = True

    def _app_factory() -> FastAPI:
        app = create_app()
        app.state.browser_runtime_shutdown = _request_server_shutdown
        return app

    config = uvicorn.Config(
        _app_factory,
        factory=True,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    if parent_pid is not None:
        _start_parent_watchdog(parent_pid, _request_server_shutdown)
    server.run()
