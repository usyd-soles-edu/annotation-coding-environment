"""Launcher lifecycle smoke tests.

Runs the compiled ace-launcher binary against the real ace-server binary.
Requires:
  - The launcher to be compiled (cargo build in desktop/launcher).
  - The ace-server payload to be buildable from this checkout.

All tests use temporary runtime files and suppress browser opening via
ACE_TEST_SUPPRESS_BROWSER.  Server processes are killed in fixture teardown.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest
from ace.db.connection import create_project


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAUNCHER_DIR = _REPO_ROOT / "desktop" / "launcher"

def _find_launcher_binary() -> Path:
    """Locate the launcher crate directory for `cargo run --quiet --`."""
    cargo_toml = _LAUNCHER_DIR / "Cargo.toml"
    if cargo_toml.is_file():
        return _LAUNCHER_DIR
    pytest.skip(
        "ace-launcher crate not found — missing desktop/launcher/Cargo.toml"
    )


def _make_server_wrapper(tmp_path: Path) -> Path:
    """Create a tiny executable wrapper that runs `python -m ace`."""
    if sys.platform.startswith("win"):
        wrapper = tmp_path / "ace-server-wrapper.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{sys.executable}" -m ace %*\r\n',
            encoding="utf-8",
        )
    else:
        wrapper = tmp_path / "ace-server-wrapper"
        wrapper.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" -m ace "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    return wrapper


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _read_runtime(runtime_file: Path) -> dict:
    """Read and parse a runtime.json file."""
    return json.loads(runtime_file.read_text(encoding="utf-8"))


def _check_server_live(port: int, token: str, timeout: float = 0.5) -> bool:
    """Return True if the server accepts the launcher token via status."""
    url = f"http://127.0.0.1:{port}/api/runtime/status"
    req = Request(url, headers={"X-ACE-Launcher-Token": token})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("enabled") is True and data.get("authenticated") is True
    except Exception:
        return False


def _wait_for_server(
    port: int,
    token: str,
    deadline: float = 15.0,
    interval: float = 0.15,
) -> None:
    """Poll until the server is live or *deadline* seconds elapse."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if _check_server_live(port, token, timeout=interval):
            return
        time.sleep(interval)
    raise AssertionError(
        f"Server on :{port} did not report ready within {deadline}s"
    )



def _session_opener():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
def _run_launcher(
    launcher: Path,
    server_binary: Path,
    runtime_file: Path,
    extra_args: list[str] | None = None,
    idle_timeout: str = "300",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the launcher via `cargo run --quiet --` with test-mode env vars set."""
    env = {
        **os.environ,
        "ACE_TEST_RUNTIME_FILE": str(runtime_file),
        "ACE_TEST_SERVER_BINARY": str(server_binary),
        "ACE_TEST_IDLE_TIMEOUT": idle_timeout,
        "ACE_TEST_SUPPRESS_BROWSER": "1",
        "PYTHONPATH": str(_REPO_ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    return subprocess.run(
        ["cargo", "run", "--quiet", "--", *(extra_args or [])],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(cwd or launcher),
    )


def _kill_server(runtime_file: Path) -> None:
    """Best-effort SIGTERM to the server referenced by *runtime_file*."""
    if not runtime_file.exists():
        return
    try:
        info = _read_runtime(runtime_file)
        pid: int = info["pid"]
        os.kill(pid, signal.SIGTERM)
        # Give it a moment to exit; avoid leftover port binding.
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, KeyError, json.JSONDecodeError, OSError):
        pass


def _kill_server_info(info: dict) -> None:
    try:
        pid = int(info["pid"])
    except (KeyError, TypeError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def launcher_bin() -> Path:
    return _find_launcher_binary()


@pytest.fixture()
def server_bin(tmp_path: Path) -> Path:
    return _make_server_wrapper(tmp_path)


@pytest.fixture()
def runtime_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temp runtime file path and clean up the server afterwards."""
    rf = tmp_path / "runtime.json"
    yield rf
    _kill_server(rf)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServerStartsReachable:
    """Launcher starts server and produces a reachable runtime on localhost."""

    def test_server_reachable_after_launch(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        proc = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc.returncode == 0, (
            f"launcher exited {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

        info = _read_runtime(runtime_file)
        assert "port" in info
        assert "token" in info
        assert "pid" in info

        _wait_for_server(info["port"], info["token"])
        assert _check_server_live(info["port"], info["token"])


class TestOpenPathUrl:
    """Launching with a .ace path produces a /launch URL in suppress-browser."""

    def test_url_contains_launch_and_open(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
        tmp_path: Path,
    ) -> None:
        ace_file = tmp_path / "project.ace"
        conn = create_project(str(ace_file), "Project from launcher")
        conn.close()

        proc = _run_launcher(
            launcher_bin,
            server_bin,
            runtime_file,
            extra_args=[str(ace_file)],
        )
        assert proc.returncode == 0, (
            f"launcher exited {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

        url_line = proc.stdout.strip()
        assert "/launch?" in url_line, f"expected /launch in URL, got: {url_line}"

        parsed = urlparse(url_line)
        qs = parse_qs(parsed.query)
        assert "token" in qs
        assert "open" in qs
        opener = _session_opener()
        with opener.open(url_line, timeout=5) as response:
            body = response.read().decode("utf-8")
            final_url = response.geturl()
        assert final_url.endswith("/import")
        assert "Project from launcher" in body


class TestChromiumBrowserSmoke:
    """Chromium can load a launcher-opened ACE server URL."""

    def test_chromium_opens_launcher_url(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        proc = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc.returncode == 0
        url_line = proc.stdout.strip()

        playwright = pytest.importorskip("playwright.sync_api")
        expect = playwright.expect
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(url_line, wait_until="networkidle")
                expect(page.get_by_role("link", name="New project")).to_be_visible()
            finally:
                browser.close()

class TestReuseExistingServer:
    """Second launch reuses the same running server/runtime metadata."""

    def test_second_launch_reuses_server(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        # First launch starts the server.
        proc1 = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc1.returncode == 0

        info1 = _read_runtime(runtime_file)
        _wait_for_server(info1["port"], info1["token"])

        # Second launch should detect the live server and reuse it.
        proc2 = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc2.returncode == 0

        info2 = _read_runtime(runtime_file)
        assert info2["port"] == info1["port"]
        assert info2["token"] == info1["token"]
        assert info2["pid"] == info1["pid"]


class TestOpenPathWithActiveTabStartsFreshServer:
    """Opening a new .ace file with active old tabs starts a fresh server."""

    def test_active_old_tab_forces_new_runtime(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
        tmp_path: Path,
    ) -> None:
        proc1 = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc1.returncode == 0
        info1 = _read_runtime(runtime_file)
        _wait_for_server(info1["port"], info1["token"])

        opener = _session_opener()
        try:
            opener.open(
                Request(f"http://127.0.0.1:{info1['port']}/launch?token={info1['token']}"),
                timeout=2,
            )
        except Exception:
            pass
        opener.open(
            Request(
                f"http://127.0.0.1:{info1['port']}/api/runtime/heartbeat",
                data=b"tab_id=existing-tab",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=2,
        )

        ace_file = tmp_path / "second-project.ace"
        conn = create_project(str(ace_file), "Second project")
        conn.close()

        proc2 = _run_launcher(
            launcher_bin,
            server_bin,
            runtime_file,
            extra_args=[str(ace_file)],
        )
        assert proc2.returncode == 0

        info2 = _read_runtime(runtime_file)
        assert info2["pid"] != info1["pid"]
        assert info2["port"] != info1["port"]
        assert _check_server_live(info1["port"], info1["token"])
        assert _check_server_live(info2["port"], info2["token"])

        _kill_server_info(info1)


class TestOpenPathStartsFreshServer:
    """Opening a .ace file starts a fresh runtime even before any heartbeat."""

    def test_open_path_does_not_reuse_existing_runtime(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
        tmp_path: Path,
    ) -> None:
        proc1 = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc1.returncode == 0
        info1 = _read_runtime(runtime_file)
        _wait_for_server(info1["port"], info1["token"])

        ace_file = tmp_path / "cold-open.ace"
        conn = create_project(str(ace_file), "Cold open project")
        conn.close()

        proc2 = _run_launcher(
            launcher_bin,
            server_bin,
            runtime_file,
            extra_args=[str(ace_file)],
        )
        assert proc2.returncode == 0

        info2 = _read_runtime(runtime_file)
        assert info2["pid"] != info1["pid"]
        assert info2["port"] != info1["port"]
        assert _check_server_live(info1["port"], info1["token"])
        assert _check_server_live(info2["port"], info2["token"])

        _kill_server_info(info1)
class TestStaleRuntimeCleanup:
    """Stale runtime metadata (dead PID) is cleaned/replaced."""

    def test_stale_runtime_replaced(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        # Write a stale runtime file pointing at a dead PID and bogus port.
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text(
            json.dumps({"pid": 9999999, "port": 19999, "token": "dead-beef"}),
            encoding="utf-8",
        )

        proc = _run_launcher(launcher_bin, server_bin, runtime_file)
        assert proc.returncode == 0

        info = _read_runtime(runtime_file)
        assert info["pid"] != 9999999, "stale PID should have been replaced"
        assert info["token"] != "dead-beef", "stale token should have been replaced"

        _wait_for_server(info["port"], info["token"])


class TestHeartbeatGrace:
    """Server survives a short disconnect / heartbeat grace path."""

    def test_server_survives_brief_disconnect(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        # Use a generous idle timeout so the server stays up through the test.
        proc = _run_launcher(
            launcher_bin, server_bin, runtime_file, idle_timeout="60"
        )
        assert proc.returncode == 0

        info = _read_runtime(runtime_file)
        port, token = info["port"], info["token"]
        base = f"http://127.0.0.1:{port}"
        headers = {"X-ACE-Launcher-Token": token}

        _wait_for_server(port, token)

        opener = _session_opener()
        # Authenticate via /launch to get a session cookie.
        launch_url = f"{base}/launch?token={token}"
        try:
            opener.open(Request(launch_url), timeout=2)
        except Exception:
            pass  # redirect response; fine

        # Register a tab heartbeat.
        hb_data = b"tab_id=test-tab-1"
        hb_req = Request(
            f"{base}/api/runtime/heartbeat",
            data=hb_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        opener.open(hb_req, timeout=2)

        # Disconnect the tab.
        disc_req = Request(
            f"{base}/api/runtime/disconnect",
            data=hb_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        opener.open(disc_req, timeout=2)

        # Wait briefly — idle countdown starts but with 60s timeout, server
        # should still be alive.
        time.sleep(1)

        assert _check_server_live(port, token), (
            "server should survive a brief disconnect within the idle timeout"
        )

        # Reconnect to reset idle timer, confirming grace path.
        hb_req2 = Request(
            f"{base}/api/runtime/heartbeat",
            data=b"tab_id=test-tab-2",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        opener.open(hb_req2, timeout=2)

        assert _check_server_live(port, token)


class TestIdleShutdown:
    """Server exits after idle timeout when run with a short test timeout."""

    def test_server_exits_after_idle_timeout(
        self,
        launcher_bin: Path,
        server_bin: Path,
        runtime_file: Path,
    ) -> None:
        # Start server with a 3-second idle timeout.
        proc = _run_launcher(
            launcher_bin, server_bin, runtime_file, idle_timeout="3"
        )
        assert proc.returncode == 0

        info = _read_runtime(runtime_file)
        pid: int = info["pid"]

        # Confirm server is up.
        _wait_for_server(info["port"], info["token"])

        # Poll until the PID is gone (server shut itself down).
        shutdown_deadline = time.monotonic() + 15
        while time.monotonic() < shutdown_deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.3)
        else:
            pytest.fail(
                f"Server PID {pid} did not exit within idle-shutdown window"
            )

        assert not runtime_file.exists(), (
            "graceful idle shutdown should complete lifespan cleanup"
        )
