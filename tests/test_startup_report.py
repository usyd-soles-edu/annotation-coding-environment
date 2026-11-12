"""Packaged startup reports contain fixed codes, never exception contents."""

import builtins
import json
import sys

import pytest

from ace.__main__ import _write_startup_report, main


def test_startup_report_excludes_private_error_text(tmp_path):
    report = tmp_path / "startup.json"
    report.write_text("", encoding="utf-8")
    _write_startup_report(
        str(report), "serve", PermissionError("PRIVATE_PROJECT_PATH and token"),
    )
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "stage": "serve", "reason": "permission_denied",
    }
    report.unlink()
    _write_startup_report(str(report), "serve", RuntimeError("PRIVATE_PROJECT_PATH"))
    assert not report.exists()


def test_app_import_failure_writes_safe_report(tmp_path, monkeypatch):
    report = tmp_path / "startup.json"
    report.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["ace", "--startup-report", str(report)])
    original_import = builtins.__import__

    def missing_app(name, *args, **kwargs):
        if name == "ace.app":
            raise ModuleNotFoundError("PRIVATE_PROJECT_PATH", name="secret_module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_app)
    with pytest.raises(ModuleNotFoundError):
        main()
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "stage": "import", "reason": "missing_dependency",
    }
