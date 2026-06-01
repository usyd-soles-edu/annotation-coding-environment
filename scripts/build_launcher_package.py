#!/usr/bin/env python3
"""Build the ACE browser launcher package.

Usage:
    uv run python scripts/build_launcher_package.py          # full build
    uv run python scripts/build_launcher_package.py --check   # verify config only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_DIR = ROOT / "desktop" / "launcher"
RESOURCES_DIR = LAUNCHER_DIR / "resources"
OUTPUT_DIR = LAUNCHER_DIR / "target" / "release"

def _platform_formats() -> list[str]:
    if sys.platform == "darwin":
        return ["app", "dmg"]
    if sys.platform.startswith("win"):
        return ["nsis", "wix"]
    raise RuntimeError(f"Unsupported packaging host platform: {sys.platform}")


def _temporary_packager_config() -> Path:
    base = (LAUNCHER_DIR / "Packager.toml").read_text(encoding="utf-8")
    formats_line = 'formats = ["app", "dmg", "nsis", "wix"]'
    override = f'formats = { _platform_formats()!r }'.replace("'", '"')
    if formats_line not in base:
        raise RuntimeError("Packager.toml missing expected formats line")
    content = base.replace(formats_line, override, 1)
    content = content.replace('before-packaging-command = "cargo build --release"\n', "", 1)
    with tempfile.NamedTemporaryFile(
        dir=LAUNCHER_DIR,
        mode="w",
        encoding="utf-8",
        suffix=".toml",
        prefix="ace-packager-",
        delete=False,
    ) as handle:
        handle.write(content)
        return Path(handle.name)


def _check() -> None:
    """Verify key files and config exist without packaging."""
    errors: list[str] = []

    packager_toml = LAUNCHER_DIR / "Packager.toml"
    if not packager_toml.exists():
        errors.append(f"Missing: {packager_toml}")
    else:
        content = packager_toml.read_text(encoding="utf-8")
        for field in ("product-name", "identifier", "version", "binaries", "resources"):
            if field not in content:
                errors.append(f"Packager.toml missing field: {field}")

    cargo_toml = LAUNCHER_DIR / "Cargo.toml"
    if not cargo_toml.exists():
        errors.append(f"Missing: {cargo_toml}")

    launcher_src = LAUNCHER_DIR / "src" / "main.rs"
    if not launcher_src.exists():
        errors.append(f"Missing: {launcher_src}")

    resources_dir = RESOURCES_DIR

    icons_dir = LAUNCHER_DIR / "icons"
    if not icons_dir.exists():
        errors.append(f"Missing icons: {icons_dir}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("Check passed: Packager.toml, Cargo.toml, launcher source, icons present.")
    if not resources_dir.exists():
        print(
            "NOTE: launcher resources/ does not exist yet. "
            "Run build_sidecar.py before packaging.",
            file=sys.stderr,
        )
        return
    if not list(resources_dir.glob("ace-server-*")):
        print(
            "NOTE: No ace-server-* binaries in resources/ yet. "
            "Run build_sidecar.py before packaging.",
            file=sys.stderr,
        )



def _cleanup_failed_build() -> None:
    """Remove copied sidecar payloads and partial installer outputs after failure."""
    if RESOURCES_DIR.exists():
        for path in RESOURCES_DIR.glob("ace-server-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    if OUTPUT_DIR.exists():
        for pattern in ("*.dmg", "*.exe", "*.msi"):
            for path in OUTPUT_DIR.rglob(pattern):
                path.unlink(missing_ok=True)
        for path in OUTPUT_DIR.rglob("*.app"):
            shutil.rmtree(path, ignore_errors=True)

def _build() -> None:
    """Build sidecar, build launcher release binary, run cargo packager."""
    temp_config: Path | None = None
    try:
        # Step 1: Build sidecar (copies to launcher resources)
        print("=== Building ACE server sidecar ===")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_sidecar.py")],
            check=True,
            cwd=str(ROOT),
        )

        # Step 2: Build launcher release binary
        print("=== Building launcher release ===")
        subprocess.run(
            ["cargo", "build", "--release"],
            check=True,
            cwd=str(LAUNCHER_DIR),
        )

        # Step 3: Package using host-specific formats only.
        temp_config = _temporary_packager_config()
        print(f"=== Running cargo packager for formats: {', '.join(_platform_formats())} ===")
        subprocess.run(
            ["cargo", "packager", "--release", "-c", str(temp_config)],
            check=True,
            cwd=str(LAUNCHER_DIR),
        )
    except Exception:
        _cleanup_failed_build()
        raise
    finally:
        if temp_config is not None:
            temp_config.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the ACE browser launcher package.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify key files/config exist without packaging.",
    )
    args = parser.parse_args()

    if args.check:
        _check()
    else:
        _build()


if __name__ == "__main__":
    main()
