"""Tests for native OS file picker endpoints."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ace.routes.api import router
from ace.routes.api_support import check_native_picker_runtime

# Build a minimal FastAPI app around the router for testing.
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _mock_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._run_osascript")
def test_pick_file_returns_path(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(0, "/tmp/test.ace\n")

    response = client.post("/api/native/pick-file", data={"accept": ".ace"})

    assert response.status_code == 200
    assert response.json() == {"path": "/tmp/test.ace"}
    mock_osascript.assert_called_once()
    # Verify the osascript includes the type filter.
    script_arg = mock_osascript.call_args[0][0]
    assert 'of type {"ace"}' in script_arg


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._run_osascript")
def test_pick_file_returns_empty_on_cancel(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(1, "", "User canceled. (-128)")

    response = client.post("/api/native/pick-file")

    assert response.status_code == 200
    assert response.json() == {"path": ""}


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._run_osascript")
def test_pick_file_reports_native_failure(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(1, "", "Permission denied. (-1743)")

    response = client.post("/api/native/pick-file")

    assert response.status_code == 503
    assert response.json() == {"path": ""}


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._run_osascript")
def test_pick_folder_returns_path(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(0, "/tmp/my_folder/\n")

    response = client.post("/api/native/pick-folder")

    assert response.status_code == 200
    assert response.json() == {"path": "/tmp/my_folder/"}
    mock_osascript.assert_called_once()


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._run_osascript")
def test_pick_files_returns_multiple_paths(mock_osascript, mock_platform):
    mock_platform.system.return_value = "Darwin"
    mock_osascript.return_value = _mock_result(
        0, "/tmp/a.csv\n/tmp/b.xlsx\n"
    )

    response = client.post(
        "/api/native/pick-files", data={"accept": ".csv,.xlsx"}
    )

    assert response.status_code == 200
    assert response.json() == {"paths": ["/tmp/a.csv", "/tmp/b.xlsx"]}
    script_arg = mock_osascript.call_args[0][0]
    assert 'of type {"csv", "xlsx"}' in script_arg


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._tk_pick_file", return_value="/tmp/test.ace")
def test_non_darwin_uses_tkinter_file(mock_tk, mock_platform):
    """Non-macOS platforms fall back to tkinter file picker."""
    mock_platform.system.return_value = "Linux"
    r = client.post("/api/native/pick-file", data={"accept": ".ace"})
    assert r.json() == {"path": "/tmp/test.ace"}
    mock_tk.assert_called_once()


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._tk_pick_folder", return_value="/tmp/my_folder")
def test_non_darwin_uses_tkinter_folder(mock_tk, mock_platform):
    """Non-macOS platforms fall back to tkinter folder picker."""
    mock_platform.system.return_value = "Linux"
    r = client.post("/api/native/pick-folder")
    assert r.json() == {"path": "/tmp/my_folder"}
    mock_tk.assert_called_once()


@patch("ace.routes.api_project_import.platform")
@patch("ace.routes.api_project_import._tk_pick_files", return_value=["/tmp/a.csv", "/tmp/b.csv"])
def test_non_darwin_uses_tkinter_files(mock_tk, mock_platform):
    """Non-macOS platforms fall back to tkinter multi-file picker."""
    mock_platform.system.return_value = "Linux"
    r = client.post("/api/native/pick-files", data={"accept": ".csv"})
    assert r.json() == {"paths": ["/tmp/a.csv", "/tmp/b.csv"]}
    mock_tk.assert_called_once()


@patch("ace.routes.api_support.platform.system", return_value="Darwin")
@patch("ace.routes.api_support._run_osascript")
def test_packaged_picker_preflight_checks_applescript(mock_osascript, _platform):
    mock_osascript.return_value = _mock_result(0, "1\n")

    check_native_picker_runtime()

    mock_osascript.assert_called_once_with("return 1", timeout=10)


@patch("ace.routes.api_support.platform.system", return_value="Darwin")
@patch("ace.routes.api_support._run_osascript")
def test_packaged_picker_preflight_rejects_failed_applescript(mock_osascript, _platform):
    mock_osascript.return_value = _mock_result(1, "", "osascript failed")

    with pytest.raises(RuntimeError, match="AppleScript picker runtime"):
        check_native_picker_runtime()


@patch("ace.routes.api_support.platform.system", return_value="Windows")
@patch("ace.routes.api_support._tk_root")
def test_packaged_picker_preflight_loads_and_closes_tk(mock_root, _platform):
    check_native_picker_runtime()

    mock_root.assert_called_once_with()
    mock_root.return_value.destroy.assert_called_once_with()


def test_picker_preflight_cli_exits_without_starting_server(monkeypatch):
    from ace.__main__ import main

    monkeypatch.setattr(sys, "argv", ["ace", "--check-native-picker"])
    with (
        patch("ace.routes.api_support.check_native_picker_runtime") as check,
        patch("ace.__main__.run") as run,
    ):
        main()
    check.assert_called_once_with()
    run.assert_not_called()
