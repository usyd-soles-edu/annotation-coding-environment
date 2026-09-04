import subprocess
import sys
from pathlib import Path

from ace import __version__


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_release_metadata.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_metadata_is_consistent():
    result = _run()

    assert result.returncode == 0, result.stderr
    assert f"Release metadata is consistent for {__version__}." in result.stdout


def test_release_metadata_rejects_an_unknown_changelog_version():
    result = _run("--print-changelog", "0.0.0")

    assert result.returncode == 1
    assert "CHANGELOG.md has no 0.0.0 section" in result.stderr


def test_current_changelog_section_is_not_empty():
    result = _run("--print-changelog", __version__)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
