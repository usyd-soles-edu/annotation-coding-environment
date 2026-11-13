"""Launcher startup reports retain only safe diagnostic codes."""

import errno
import json

from ace.__main__ import _write_startup_report


def test_startup_report_names_only_known_missing_dependencies(tmp_path):
    report = tmp_path / "startup.json"
    report.write_text("", encoding="utf-8")
    _write_startup_report(
        str(report), "import", ModuleNotFoundError("PRIVATE_SENTINEL", name="fastapi")
    )
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "stage": "import", "reason": "missing_dependency", "detail": "fastapi"
    }

    _write_startup_report(
        str(report), "import", ModuleNotFoundError("PRIVATE_SENTINEL", name="private_project")
    )
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "stage": "import", "reason": "missing_dependency"
    }


def test_startup_report_excludes_os_error_text_and_path(tmp_path):
    report = tmp_path / "startup.json"
    report.write_text("", encoding="utf-8")
    error = OSError(errno.ENOSPC, "PRIVATE_SENTINEL", "/private/project.ace")
    _write_startup_report(str(report), "serve", error)
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "stage": "serve", "reason": "os_error", "detail": "disk_full"
    }
