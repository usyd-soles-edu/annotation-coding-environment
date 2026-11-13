#!/usr/bin/env python3
"""Compile ACE server for the browser launcher.

Uses a standalone Nuitka bundle on macOS because current onefile output trips
macOS code-signing validation when executed from the packaged app. Other
platforms keep the onefile build for smaller packaging.

The compiled payload is placed in `desktop/launcher/resources/` for
cargo-packager to bundle into the installer.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TRIPLES = {
    ("darwin", "aarch64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
}


def get_host_triple() -> str:
    """Get the Rust target triple for the current host."""
    result = subprocess.run(
        ["rustc", "-vV"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Could not determine host triple from rustc")


def _macos_standalone_dist(build_dir: Path) -> Path:
    matches = sorted(build_dir.glob("*.dist"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one standalone dist dir in {build_dir}, found: {matches}"
        )
    return matches[0]


def _clean_dest(path: Path) -> None:
    """Remove a previous build output (file or directory) if it exists."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def main() -> None:
    triple = get_host_triple()
    macos = "darwin" in triple

    ext = ".exe" if "windows" in triple else ""
    binary_name = f"ace-server-{triple}{ext}"
    build_dir = Path(tempfile.gettempdir()) / "ace-build"

    print(f"Compiling ACE for {triple}...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src"))

    if macos:
        mode_args = ["--standalone", "--nofollow-import-to=tkinter", "--nofollow-import-to=_tkinter"]
    else:
        mode_args = ["--onefile", f"--onefile-tempdir-spec={{CACHE_DIR}}/ace-coder"]

    cmd = [
        sys.executable, "-m", "nuitka",
        *mode_args,
        f"--output-dir={build_dir}",
        f"--output-filename={binary_name}",
        "--include-package=ace",
        "--include-data-dir=src/ace/static=ace/static",
        "--include-data-dir=src/ace/templates=ace/templates",
        "--assume-yes-for-downloads",
        str(Path("src/ace/__main__.py")),
    ]
    if "windows" in triple:
        cmd.insert(-1, "--enable-plugin=tk-inter")

    subprocess.run(cmd, check=True, env=env)

    launcher_resources = Path("desktop/launcher/resources")
    launcher_resources.mkdir(parents=True, exist_ok=True)

    if macos:
        dest = launcher_resources / f"{binary_name}.dist"
        _clean_dest(dest)
        shutil.copytree(_macos_standalone_dist(build_dir), dest)
        print(f"Standalone server bundle placed at {dest}")
    else:
        dest = launcher_resources / binary_name
        binary = build_dir / binary_name
        if not binary.exists():
            sys.exit(f"ERROR: compiled binary not found at {binary}")
        _clean_dest(dest)
        shutil.copy2(str(binary), str(dest))
        print(f"Binary placed at {dest} ({dest.stat().st_size // (1024*1024)} MB)")


if __name__ == "__main__":
    main()
