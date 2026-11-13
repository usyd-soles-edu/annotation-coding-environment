#!/usr/bin/env python3
"""Check that the previous packaged Windows server survives a new version.

CI supplies the previous release MSI. The installers are extracted into
temporary directories; neither is installed or published by this check.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request, build_opener, urlopen

from smoke_packaged_server import request_json, stage_package


@dataclass
class PackagedServer:
    process: subprocess.Popen
    port: int
    token: str
    opener: OpenerDirector


def stage_previous_msi(installer: Path, directory: Path) -> Path:
    if not installer.is_file() or installer.suffix.lower() != ".msi":
        raise RuntimeError("Previous Windows MSI was not found")
    directory.mkdir()
    subprocess.run(
        ["msiexec.exe", "/a", str(installer), "/qn", f"TARGETDIR={directory}"],
        check=True,
        timeout=180,
    )
    launchers = list(directory.rglob("ace-launcher.exe"))
    sidecars = list(directory.rglob("ace-server-*-windows-msvc.exe"))
    if len(launchers) != 1 or len(sidecars) != 1:
        raise RuntimeError("Previous MSI has no unique launcher and server")
    return sidecars[0]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_closed(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return False
    except OSError:
        return True


def force_stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        if sys.platform.startswith("win"):
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Packaged server process tree did not stop") from error


def assert_alive(server: PackagedServer) -> None:
    request = Request(
        f"http://127.0.0.1:{server.port}/api/runtime/status",
        headers={"X-ACE-Launcher-Token": server.token},
    )
    try:
        with urlopen(request, timeout=2) as response:
            status = json.load(response)
    except (OSError, ValueError):
        raise RuntimeError("Packaged server stopped responding") from None
    if status.get("enabled") is not True or status.get("authenticated") is not True:
        raise RuntimeError("Packaged server did not authenticate its token")


def start_server(binary: Path, directory: Path) -> PackagedServer:
    port = free_port()
    token = secrets.token_urlsafe(24)
    child_env = os.environ.copy()
    for key in (
        "PYTHONPATH", "PYTHONHOME", "ACE_TEST_SERVER_BINARY", "ACE_LAUNCHER_TOKEN",
        "ACE_RUNTIME_FILE", "ACE_TEST_RUNTIME_FILE",
    ):
        child_env.pop(key, None)
    process = subprocess.Popen(
        [
            str(binary), "--port", str(port), "--launcher-token", token,
            "--idle-timeout-seconds", "120", "--no-kill-stale",
        ],
        cwd=directory,
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    server = PackagedServer(process, port, token, opener)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Packaged server exited before readiness")
            try:
                assert_alive(server)
                break
            except RuntimeError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Packaged server did not become ready")
        try:
            with opener.open(
                f"http://127.0.0.1:{port}/launch?token={quote(token, safe='')}",
                timeout=5,
            ):
                pass
        except (HTTPError, URLError, OSError):
            raise RuntimeError("Packaged server did not establish a launch session") from None
        return server
    except BaseException:
        force_stop(process)
        raise


def stop_server(server: PackagedServer) -> None:
    try:
        request_json(
            server.opener, f"http://127.0.0.1:{server.port}/api/runtime/quit", data={}
        )
    except OSError:
        pass
    try:
        server.process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        force_stop(server.process)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not port_closed(server.port):
        time.sleep(0.1)
    if not port_closed(server.port):
        raise RuntimeError("Packaged server listener remained open after shutdown")


def smoke(previous_msi: Path) -> None:
    if not sys.platform.startswith("win"):
        raise RuntimeError("The packaged upgrade smoke requires Windows")
    with tempfile.TemporaryDirectory(prefix="ace-windows-upgrade-") as directory:
        temp = Path(directory)
        previous_binary = stage_previous_msi(previous_msi, temp / "previous")
        (temp / "current").mkdir()
        _, current_binary = stage_package(temp / "current")
        previous: PackagedServer | None = None
        current: PackagedServer | None = None
        try:
            previous = start_server(previous_binary, temp)
            current = start_server(current_binary, temp)
            if previous.process.pid == current.process.pid or previous.port == current.port:
                raise RuntimeError("Packaged servers did not start independently")
            assert_alive(previous)
            assert_alive(current)
        finally:
            try:
                if current is not None:
                    stop_server(current)
            finally:
                if previous is not None:
                    stop_server(previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous_msi", type=Path)
    args = parser.parse_args()
    smoke(args.previous_msi)
    print("Previous and current packaged Windows servers ran concurrently")
