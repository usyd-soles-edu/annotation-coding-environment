"""Validate desktop/launcher/Packager.toml configuration."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
PACKAGER_TOML = ROOT / "desktop" / "launcher" / "Packager.toml"
LAUNCHER_CARGO_TOML = ROOT / "desktop" / "launcher" / "Cargo.toml"


def _load() -> dict:
    return tomllib.loads(PACKAGER_TOML.read_text(encoding="utf-8"))


def test_packager_toml_exists():
    assert PACKAGER_TOML.exists(), f"Missing: {PACKAGER_TOML}"


def test_product_name():
    cfg = _load()
    assert cfg["product-name"] == "ACE"


def test_identifier():
    cfg = _load()
    assert cfg["identifier"] == "au.edu.sydney.ace-coder"


def test_version_matches_launcher():
    cfg = _load()
    launcher = tomllib.loads(LAUNCHER_CARGO_TOML.read_text(encoding="utf-8"))
    assert cfg["version"] == launcher["package"]["version"]


def test_formats_restrict_to_macos_and_windows_outputs():
    cfg = _load()
    assert cfg["formats"] == ["app", "dmg", "nsis", "wix"]



def test_file_association_includes_ace():
    cfg = _load()
    associations = cfg.get("file-associations", [])
    assert len(associations) >= 1
    exts = associations[0].get("extensions", [])
    assert "ace" in exts, f"Expected 'ace' in extensions, got {exts}"


def test_resources_use_exact_sidecar_payload_paths():
    cfg = _load()
    resources = cfg.get("resources", [])
    assert "resources/ace-server-aarch64-apple-darwin.dist" in resources
    assert "resources/ace-server-x86_64-apple-darwin.dist" in resources
    assert "resources/ace-server-x86_64-pc-windows-msvc.exe" in resources
    assert all(isinstance(resource, str) for resource in resources), resources
    assert all("*" not in resource for resource in resources), resources


def test_binaries_declared():
    cfg = _load()
    binaries = cfg.get("binaries", [])
    assert len(binaries) >= 1
    assert binaries[0].get("main") is True


def test_macos_sections_present():
    cfg = _load()
    assert "macos" in cfg, "Missing [macos] section (app bundle)"
    assert "dmg" in cfg, "Missing [dmg] section"
    assert "application-folder-position" in cfg["dmg"]


def test_windows_sections_present():
    cfg = _load()
    assert "nsis" in cfg, "Missing [nsis] section"
    assert "wix" in cfg, "Missing [wix] section (MSI)"
    assert cfg["nsis"].get("installer-mode") == "currentUser"


def test_icons_reference_existing_files():
    cfg = _load()
    icons = cfg.get("icons", [])
    assert len(icons) >= 1, "Must declare at least one icon"
    icons_dir = ROOT / "desktop" / "launcher" / "icons"
    for icon in icons:
        resolved = (ROOT / "desktop" / "launcher" / icon).resolve()
        assert resolved.exists(), f"Icon not found: {icon} → {resolved}"


def test_icons_do_not_reference_old_desktop_shell():
    cfg = _load()
    icons = cfg.get("icons", [])
    for icon in icons:
        assert "src-tauri" not in icon, (
            f"Icon path still references src-tauri: {icon}. "
            "Icons should be in desktop/launcher/icons/."
        )
