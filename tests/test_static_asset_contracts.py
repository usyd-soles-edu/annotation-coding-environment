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


def test_coding_keyboard_module_loads_before_bridge():
    base = (ROOT / "src" / "ace" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    keyboard_idx = base.index("/static/js/coding_keyboard.js")
    bridge_idx = base.index("/static/js/bridge.js")
    assert keyboard_idx < bridge_idx


def test_source_horizontal_sentence_aliases_removed():
    bridge = (ROOT / "src" / "ace" / "static" / "js" / "bridge.js").read_text(
        encoding="utf-8"
    )
    assert "Aliases for ↑ / ↓" not in bridge
    assert "sentencesR" not in bridge
    assert "sentencesL" not in bridge


def test_audit_codebook_mutations_send_mode_context():
    bridge = (ROOT / "src" / "ace" / "static" / "js" / "bridge.js").read_text(
        encoding="utf-8"
    )
    tree_source = (
        ROOT / "src" / "ace" / "static" / "js" / "codebook_headless_tree_source.js"
    ).read_text(encoding="utf-8")

    assert "function _codebookMutationValues" in bridge
    assert "next.codebook_mode = ctx.mode" in bridge
    assert "next.current_code_id = ctx.currentCodeId" in bridge
    assert "_codebookMutationQueryString" in bridge

    assert "function codebookMutationValues" in tree_source
    assert "next.codebook_mode = ctx.mode" in tree_source
    assert "next.current_code_id = ctx.currentCodeId" in tree_source
    assert "values: codebookMutationValues(values)" in tree_source


def test_headless_tree_controller_exposes_mode_policy_contract():
    tree_source = (
        ROOT / "src" / "ace" / "static" / "js" / "codebook_headless_tree_source.js"
    ).read_text(encoding="utf-8")

    assert "const MODE_POLICIES = Object.freeze" in tree_source
    assert "getMode: currentCodebookMode" in tree_source
    assert "modePolicy: function () { return { ...modePolicy() }; }" in tree_source
    assert "isCodingMode" in tree_source
    assert "isAuditMode" in tree_source
    assert "isReadonlyMode" in tree_source
