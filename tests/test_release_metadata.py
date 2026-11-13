import importlib.util
import subprocess
import sys
from pathlib import Path

from ace import __version__


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_release_metadata.py"
_SPEC = importlib.util.spec_from_file_location("check_release_metadata", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
check_release_metadata = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_release_metadata)


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


def test_tagged_release_requires_citation_date(tmp_path, monkeypatch):
    (tmp_path / "CITATION.cff").write_text('version: "1.8.0"\n', encoding="utf-8")
    monkeypatch.setattr(
        check_release_metadata,
        "release_versions",
        lambda _root: {"src/ace/__init__.py": "1.8.0"},
    )

    errors = check_release_metadata.validate_release_metadata(
        root=tmp_path, expected_tag="v1.8.0"
    )

    assert errors == ["CITATION.cff needs date-released for v1.8.0"]


def test_tagged_release_accepts_matching_citation_date(tmp_path, monkeypatch):
    (tmp_path / "CITATION.cff").write_text(
        'version: "1.8.0"\ndate-released: "2026-11-13"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        check_release_metadata,
        "release_versions",
        lambda _root: {"src/ace/__init__.py": "1.8.0"},
    )
    monkeypatch.setattr(check_release_metadata, "_tag_date", lambda *_: "2026-11-13")

    assert check_release_metadata.validate_release_metadata(
        root=tmp_path, expected_tag="v1.8.0"
    ) == []
