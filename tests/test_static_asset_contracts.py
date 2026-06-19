import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_headless_tree_distribution_matches_source():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_headless_tree_sync.py"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_base_template_loads_notes_module_before_bridge():
    base = (ROOT / "src" / "ace" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    notes_idx = base.index("/static/js/ace_notes.js")
    bridge_idx = base.index("/static/js/bridge.js")
    assert notes_idx < bridge_idx


def test_notes_module_exposes_lifecycle_contract():
    notes = (ROOT / "src" / "ace" / "static" / "js" / "ace_notes.js").read_text(
        encoding="utf-8"
    )
    assert "window.aceInitNotes = aceInitNotes" in notes
    assert 'document.addEventListener("htmx:load"' in notes


def test_notes_module_exposes_drawer_state_contract():
    notes = (ROOT / "src" / "ace" / "static" / "js" / "ace_notes.js").read_text(
        encoding="utf-8"
    )
    assert "window.aceIsNoteDrawerOpen = _isDrawerOpen" in notes
