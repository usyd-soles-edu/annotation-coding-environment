"""Controlled response tests for audit-view navigation race handling."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_audit_navigation_ignores_superseded_responses():
    script = Path(__file__).parent / "js" / "code_view_navigation.cjs"
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
