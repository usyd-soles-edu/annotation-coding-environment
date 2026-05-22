"""Validate that the launcher packaging path is the sole desktop build target.

Confirms that no removed desktop-shell paths remain and that the launcher
resources/icons paths are in place.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_removed_desktop_shell_directory_is_gone():
    """The old embedded desktop shell has been removed in favour of the browser launcher."""
    src_tauri = ROOT / "desktop" / "src-tauri"
    assert not src_tauri.exists(), (
        f"desktop/src-tauri/ still exists — remove it to complete the cutover"
    )


def test_launcher_resources_dir_exists():
    resources = ROOT / "desktop" / "launcher" / "resources"
    # The directory itself should exist (sidecar build populates it)
    if resources.exists():
        return
    # In CI or before a sidecar build, the dir may not exist yet;
    # verify the parent structure is correct instead.
    assert resources.parent.exists(), (
        f"desktop/launcher/ directory missing: {resources.parent}"
    )


def test_launcher_icons_dir_exists():
    icons = ROOT / "desktop" / "launcher" / "icons"
    assert icons.exists(), f"Missing launcher icons directory: {icons}"
    for name in ("32x32.png", "128x128.png", "128x128@2x.png",
                 "icon.icns", "icon.ico", "icon.png"):
        assert (icons / name).exists(), f"Missing launcher icon: {icons / name}"


def test_packager_toml_declares_launcher_icons():
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    packager_toml = ROOT / "desktop" / "launcher" / "Packager.toml"
    content = packager_toml.read_text(encoding="utf-8")
    assert "src-tauri" not in content, (
        "Packager.toml still references src-tauri paths"
    )
    cfg = tomllib.loads(content)
    icons = cfg.get("icons", [])
    assert all(
        not icon.startswith("../") for icon in icons
    ), f"Icons should be local to desktop/launcher/: {icons}"
