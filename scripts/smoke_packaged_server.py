#!/usr/bin/env python3
"""Exercise the freshly packaged launcher and bundled server before upload.

Run after ``build_launcher_package.py`` on macOS or Windows. The child is run
without PYTHONPATH or a server-binary override so missing bundled Python,
templates, or static files fail this check. All project/runtime files are
created in a temporary directory and the runtime is shut down afterward.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from ace.db.connection import create_project


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "desktop" / "launcher" / "target" / "release"


def stage_package(directory: Path) -> tuple[Path, Path]:
    """Copy/extract the distributable away from checkout fallback paths."""
    if sys.platform == "darwin":
        source = RELEASE_DIR / "ACE.app"
        if not source.is_dir():
            raise RuntimeError(f"Packaged application was not found at {source}")
        package = directory / "ACE.app"
        shutil.copytree(source, package)
        launcher = package / "Contents" / "MacOS" / "ace-launcher"
        sidecars = list((package / "Contents" / "Resources").glob(
            "ace-server-*.dist/ace-server-*"
        ))
    elif sys.platform.startswith("win"):
        installers = list(RELEASE_DIR.glob("*.msi"))
        if len(installers) != 1:
            raise RuntimeError("Expected exactly one packaged Windows MSI")
        package = directory / "extracted-msi"
        package.mkdir()
        subprocess.run(
            ["msiexec.exe", "/a", str(installers[0]), "/qn", f"TARGETDIR={package}"],
            check=True,
            timeout=180,
        )
        launchers = list(package.rglob("ace-launcher.exe"))
        sidecars = list(package.rglob("ace-server-*-windows-msvc.exe"))
        if len(launchers) != 1:
            raise RuntimeError("Extracted MSI has no unique ACE launcher")
        launcher = launchers[0]
    else:
        raise RuntimeError("Packaged smoke is supported on macOS and Windows")
    if not launcher.is_file() or len(sidecars) != 1 or not sidecars[0].is_file():
        raise RuntimeError("Packaged launcher or bundled server payload is missing")
    return launcher, sidecars[0]


def request_json(opener, url: str, *, data: dict | None = None) -> dict:
    body = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=body)
    with opener.open(request, timeout=5) as response:
        return json.load(response)


def runtime_stopped(runtime_file: Path, port: int) -> bool:
    if runtime_file.exists():
        return False
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/runtime/status", timeout=0.2):
            return False
    except HTTPError:
        return False
    except (OSError, URLError):
        return True


def smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="ace-packaged-smoke-") as directory:
        temp = Path(directory)
        launcher, sidecar = stage_package(temp)
        project = temp / "smoke.ace"
        create_project(project, "Packaged smoke").close()
        runtime_file = temp / "runtime.json"

        child_env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "ACE_TEST_SERVER_BINARY", "ACE_LAUNCHER_TOKEN", "ACE_RUNTIME_FILE"):
            child_env.pop(key, None)
        child_env.update({
            "ACE_TEST_RUNTIME_FILE": str(runtime_file),
            "ACE_TEST_SUPPRESS_BROWSER": "1",
            "ACE_TEST_IDLE_TIMEOUT": "60",
        })

        picker_check = subprocess.run(
            [str(sidecar), "--check-native-picker"],
            cwd=temp,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if picker_check.returncode != 0:
            raise RuntimeError(
                "Packaged server cannot load native picker runtime: "
                f"{picker_check.stderr.strip()}"
            )

        port: int | None = None
        pid: int | None = None
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            try:
                launched = subprocess.run(
                    [str(launcher), str(project)],
                    cwd=temp,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError("Packaged launcher timed out during startup") from None
            if launched.returncode != 0:
                raise RuntimeError("Packaged launcher failed to start its bundled server")
            if not runtime_file.is_file():
                raise RuntimeError("Packaged launcher did not write runtime metadata")
            runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
            pid = int(runtime["pid"])
            port = int(runtime["port"])
            token = str(runtime["token"])

            lines = launched.stdout.strip().splitlines()
            launch_url = lines[-1] if lines else ""
            parsed = urlparse(launch_url)
            query = parse_qs(parsed.query)
            if (
                parsed.scheme != "http"
                or parsed.hostname != "127.0.0.1"
                or parsed.port != port
                or parsed.path != "/launch"
                or query.get("token") != [token]
                or query.get("open") != [str(project)]
            ):
                raise RuntimeError("Packaged launcher returned an invalid launch URL")

            status_request = Request(
                f"http://127.0.0.1:{port}/api/runtime/status",
                headers={"X-ACE-Launcher-Token": token},
            )
            with urlopen(status_request, timeout=5) as response:
                status = json.load(response)
            if status.get("enabled") is not True or status.get("authenticated") is not True:
                raise RuntimeError("Bundled server did not authenticate its launcher")

            with opener.open(launch_url, timeout=10) as response:
                page = response.read().decode("utf-8")
                final_path = urlparse(response.geturl()).path
            if final_path != "/import" or "Choose your source data" not in page:
                raise RuntimeError("Bundled import template did not render for an opened project")

            base = f"http://127.0.0.1:{port}"
            for asset, marker in (
                ("/static/css/ace.css", "--ace-bg"),
                ("/static/js/bridge.js", "use strict"),
            ):
                with opener.open(base + asset, timeout=5) as response:
                    content = response.read().decode("utf-8")
                if marker not in content:
                    raise RuntimeError(f"Bundled asset failed its smoke check: {asset}")

            heartbeat = request_json(
                opener, base + "/api/runtime/heartbeat", data={"tab_id": "packaged-smoke"}
            )
            if heartbeat.get("active_tabs") != 1:
                raise RuntimeError("Bundled runtime heartbeat did not register")
            disconnect = request_json(
                opener, base + "/api/runtime/disconnect", data={"tab_id": "packaged-smoke"}
            )
            if disconnect.get("active_tabs") != 0:
                raise RuntimeError("Bundled runtime disconnect did not unregister")
            request_json(opener, base + "/api/runtime/quit", data={})

            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not runtime_stopped(runtime_file, port):
                time.sleep(0.1)
            if not runtime_stopped(runtime_file, port):
                raise RuntimeError("Bundled runtime did not shut down cleanly")

            # A missing packaged payload must fail even if this checkout has
            # a development sidecar in desktop/launcher/resources.
            held_sidecar = temp / "held-sidecar"
            sidecar.rename(held_sidecar)
            missing_payload = subprocess.run(
                [str(launcher), str(project)],
                cwd=temp,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if missing_payload.returncode == 0 or runtime_file.exists():
                raise RuntimeError("Launcher found a server outside the staged package")
        finally:
            # A failed or timed-out launcher may already have spawned the
            # server before this function read its runtime metadata.
            if runtime_file.is_file():
                try:
                    remaining = json.loads(runtime_file.read_text(encoding="utf-8"))
                    pid = int(remaining["pid"])
                    port = int(remaining["port"])
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    pass
            if pid is not None and port is not None and not runtime_stopped(runtime_file, port):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                runtime_file.unlink(missing_ok=True)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not runtime_stopped(runtime_file, port):
                    time.sleep(0.1)
            runtime_file.unlink(missing_ok=True)


if __name__ == "__main__":
    smoke()
    print("Packaged launcher and bundled server smoke passed")
