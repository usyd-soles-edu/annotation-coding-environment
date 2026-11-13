#!/usr/bin/env python3
"""Keep the previous packaged Windows server alive while starting this build.

The old MSI is supplied by CI from the last published release. Both installers
are extracted into temporary directories, without installing either version.
"""

from __future__ import annotations

import argparse
import ctypes
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from smoke_packaged_server import request_json, runtime_stopped, stage_package


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
    return launchers[0]


def start_runtime(launcher: Path, runtime_file: Path, directory: Path) -> tuple[int, int]:
    child_env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "ACE_TEST_SERVER_BINARY", "ACE_LAUNCHER_TOKEN", "ACE_RUNTIME_FILE"):
        child_env.pop(key, None)
    child_env.update({
        "ACE_TEST_RUNTIME_FILE": str(runtime_file),
        "ACE_TEST_SUPPRESS_BROWSER": "1",
        "ACE_TEST_IDLE_TIMEOUT": "120",
    })
    launched = subprocess.run(
        [str(launcher)], cwd=directory, env=child_env,
        capture_output=True, text=True, timeout=90,
    )
    if launched.returncode != 0 or not runtime_file.is_file():
        raise RuntimeError("Packaged launcher failed to start its server")

    runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
    pid, port, token = int(runtime["pid"]), int(runtime["port"]), str(runtime["token"])
    lines = launched.stdout.strip().splitlines()
    launch_url = lines[-1] if lines else ""
    parsed = urlparse(launch_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != port
        or parsed.path != "/launch"
        or parse_qs(parsed.query).get("token") != [token]
    ):
        raise RuntimeError("Packaged launcher returned an invalid launch URL")
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(launch_url, timeout=10):
        pass
    assert_runtime_alive(port, token)
    return pid, port


def assert_runtime_alive(port: int, token: str) -> None:
    request = Request(
        f"http://127.0.0.1:{port}/api/runtime/status",
        headers={"X-ACE-Launcher-Token": token},
    )
    with urlopen(request, timeout=5) as response:
        status = json.load(response)
    if status.get("enabled") is not True or status.get("authenticated") is not True:
        raise RuntimeError("Packaged server stopped responding to its launcher")


def process_alive(pid: int) -> bool:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: the process has exited.
            return False
        raise OSError(error, "Could not inspect packaged server process")
    try:
        return wait(handle, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        close(handle)


def stop_runtime(runtime_file: Path) -> None:
    if not runtime_file.is_file():
        return
    try:
        runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
        pid, port, token = int(runtime["pid"]), int(runtime["port"]), str(runtime["token"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        runtime_file.unlink(missing_ok=True)
        return
    try:
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with opener.open(f"http://127.0.0.1:{port}/launch?token={quote(token, safe='')}", timeout=5):
            pass
        request_json(opener, f"http://127.0.0.1:{port}/api/runtime/quit", data={})
    except OSError:
        pass

    def stopped() -> bool:
        return runtime_stopped(runtime_file, port) and not process_alive(pid)

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not stopped():
        time.sleep(0.1)
    if not stopped():
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True, timeout=10, check=False,
        )
        runtime_file.unlink(missing_ok=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not stopped():
            time.sleep(0.1)
    if not stopped():
        raise RuntimeError("Packaged server did not stop before MSI cleanup")


def smoke(previous_msi: Path) -> None:
    if not sys.platform.startswith("win"):
        raise RuntimeError("The packaged upgrade smoke requires Windows")
    with tempfile.TemporaryDirectory(prefix="ace-windows-upgrade-") as directory:
        temp = Path(directory)
        old_launcher = stage_previous_msi(previous_msi, temp / "previous")
        (temp / "current").mkdir()
        new_launcher, _ = stage_package(temp / "current")
        old_file, new_file = temp / "old-runtime.json", temp / "new-runtime.json"
        try:
            old_pid, old_port = start_runtime(old_launcher, old_file, temp)
            new_pid, new_port = start_runtime(new_launcher, new_file, temp)
            if old_pid == new_pid or old_port == new_port:
                raise RuntimeError("Packaged runtimes did not start independently")
            old_token = json.loads(old_file.read_text(encoding="utf-8"))["token"]
            assert_runtime_alive(old_port, old_token)
        finally:
            try:
                stop_runtime(new_file)
            finally:
                stop_runtime(old_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous_msi", type=Path)
    args = parser.parse_args()
    smoke(args.previous_msi)
    print("Previous and current packaged Windows servers ran concurrently")
