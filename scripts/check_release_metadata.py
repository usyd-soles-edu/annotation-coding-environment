"""Validate that every release surface identifies the same ACE version."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _match(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not read {label} from {path.relative_to(ROOT)}")
    return match.group(1)


def _toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def release_versions(root: Path = ROOT) -> dict[str, str]:
    cargo_lock = _toml(root / "desktop/launcher/Cargo.lock")
    launcher = next(
        package
        for package in cargo_lock["package"]
        if package["name"] == "ace-launcher"
    )
    changelog_versions = re.findall(
        r"^## (\d+\.\d+\.\d+)$",
        (root / "CHANGELOG.md").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not changelog_versions:
        raise ValueError("CHANGELOG.md has no release heading")

    return {
        "src/ace/__init__.py": _match(
            root / "src/ace/__init__.py",
            r'^__version__\s*=\s*["\']([^"\']+)["\']$',
            "Python version",
        ),
        "desktop/launcher/Cargo.toml": _toml(
            root / "desktop/launcher/Cargo.toml"
        )["package"]["version"],
        "desktop/launcher/Cargo.lock": launcher["version"],
        "desktop/launcher/Packager.toml": _toml(
            root / "desktop/launcher/Packager.toml"
        )["version"],
        ".zenodo.json": json.loads(
            (root / ".zenodo.json").read_text(encoding="utf-8")
        )["version"],
        "CITATION.cff": _match(
            root / "CITATION.cff",
            r'^version:\s*["\']?([^"\'\s]+)["\']?$',
            "CFF version",
        ),
        "CHANGELOG.md": changelog_versions[0],
        "README.md": _match(
            root / "README.md",
            r"\(Version (\d+\.\d+\.\d+)\)",
            "README citation version",
        ),
        "website/index.qmd": _match(
            root / "website/index.qmd",
            r"\(Version (\d+\.\d+\.\d+)\)",
            "website citation version",
        ),
    }


def changelog_section(version: str, root: Path = ROOT) -> str:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(version)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"CHANGELOG.md has no {version} section")
    body = match.group("body").strip()
    if not body:
        raise ValueError(f"CHANGELOG.md has an empty {version} section")
    return body


def _tag_date(tag: str, root: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "for-each-ref",
            "--format=%(creatordate:short)",
            f"refs/tags/{tag}",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"Could not inspect release tag {tag}")
    return result.stdout.strip()


def validate_release_metadata(
    root: Path = ROOT,
    expected_tag: str | None = None,
) -> list[str]:
    versions = release_versions(root)
    expected = expected_tag.removeprefix("v") if expected_tag else versions["src/ace/__init__.py"]
    errors = [
        f"{path} identifies {version}; expected {expected}"
        for path, version in versions.items()
        if version != expected
    ]

    release_date = _match(
        root / "CITATION.cff",
        r'^date-released:\s*["\']?([^"\'\s]+)["\']?$',
        "CFF release date",
    )
    try:
        date.fromisoformat(release_date)
    except ValueError:
        errors.append(f"CITATION.cff has invalid release date {release_date}")

    if expected_tag:
        tag_date = _tag_date(expected_tag, root)
        if release_date != tag_date:
            errors.append(
                f"CITATION.cff date-released is {release_date}; "
                f"{expected_tag} was released on {tag_date}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="release tag to compare, for example v1.6.1")
    parser.add_argument(
        "--print-changelog",
        metavar="VERSION",
        help="print the matching changelog section and exit",
    )
    args = parser.parse_args()

    try:
        if args.print_changelog:
            print(changelog_section(args.print_changelog))
            return 0
        errors = validate_release_metadata(expected_tag=args.tag)
    except (KeyError, StopIteration, ValueError) as error:
        print(f"Release metadata check failed: {error}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"Release metadata check failed: {error}", file=sys.stderr)
        return 1

    version = args.tag.removeprefix("v") if args.tag else release_versions()["src/ace/__init__.py"]
    print(f"Release metadata is consistent for {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
