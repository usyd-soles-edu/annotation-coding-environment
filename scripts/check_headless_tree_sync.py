from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ace" / "static" / "js" / "codebook_headless_tree_source.js"
DIST = ROOT / "src" / "ace" / "static" / "js" / "codebook_headless_tree.js"
BUILD = ROOT / "scripts" / "build_codebook_tree.sh"


def _check_files_exist() -> int:
    if not SOURCE.exists() or not DIST.exists() or not BUILD.exists():
        print("missing headless-tree source, distribution, or build script")
        return 1
    if "src/ace/static/js/codebook_headless_tree_source.js" not in DIST.read_text(
        encoding="utf-8"
    ):
        print("codebook_headless_tree.js does not include the source module marker")
        return 1
    print("headless-tree-contract-ok")
    return 0


def _check_rebuild_matches() -> int:
    missing = _check_files_exist()
    if missing:
        return missing

    original_dist = DIST.read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            ["bash", str(BUILD)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="")
            return result.returncode
        rebuilt_dist = DIST.read_text(encoding="utf-8")
    finally:
        DIST.write_text(original_dist, encoding="utf-8")

    if original_dist != rebuilt_dist:
        print(
            "codebook_headless_tree.js differs from "
            "a fresh build of codebook_headless_tree_source.js. Run "
            "`scripts/build_codebook_tree.sh` and commit the rebuilt bundle."
        )
        return 1
    print("headless-tree-sync-ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="rebuild the bundled JS and compare it with the committed file",
    )
    args = parser.parse_args()
    if args.rebuild:
        return _check_rebuild_matches()
    return _check_files_exist()


if __name__ == "__main__":
    raise SystemExit(main())
