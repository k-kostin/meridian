#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATH_PARTS = {
    ".claude",
    ".venv",
    ".playwright-cli",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "references",
    "superpowers",
}

FORBIDDEN_FILE_NAMES = {
    ".DS_Store",
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE_SESSION.md",
    "db.sqlite3",
    "OPEN_SOURCE_READINESS.md",
    "TWENTY_PRACTICES_FOR_WAREHOUSE.md",
    "prepare_public_repo.py",
}

REQUIRED_FILES = {
    ".gitignore",
    "LICENSE",
    "README.md",
    "docs/releases/v0.1-mvp-baseline.md",
    "manage.py",
    "requirements.txt",
}

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

FORBIDDEN_PUBLIC_TEXT = {
    "/Users/kirillkostin/Projects/warehouse",
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE_SESSION",
    "Codex",
    "Claude",
    "OPEN_SOURCE_READINESS",
    "TWENTY_PRACTICES",
    "Yandex.Disk",
    "docs/references",
    "superpowers",
}

TEXT_SUFFIXES = {
    ".bat",
    ".command",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".yml",
    ".yaml",
}


def iter_files(root: Path, *, exclude_forbidden: bool = False):
    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)
        relative_parts = current.relative_to(root).parts

        if ".git" in relative_parts:
            dirnames[:] = []
            continue

        if exclude_forbidden and any(part in FORBIDDEN_PATH_PARTS for part in relative_parts):
            dirnames[:] = []
            continue

        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname != ".git" and not (exclude_forbidden and dirname in FORBIDDEN_PATH_PARTS)
        ]

        for filename in filenames:
            yield current / filename


def check_required_files(root: Path) -> list[str]:
    return [f"missing required file: {name}" for name in sorted(REQUIRED_FILES) if not (root / name).is_file()]


def check_forbidden_paths(root: Path) -> list[str]:
    errors = []
    reported_forbidden = set()

    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)
        relative_current = current.relative_to(root)
        if ".git" in relative_current.parts:
            dirnames[:] = []
            continue

        allowed_dirnames = []
        for dirname in dirnames:
            if dirname == ".git":
                continue
            if dirname in FORBIDDEN_PATH_PARTS:
                forbidden_path = relative_current / dirname if relative_current.parts else Path(dirname)
                if forbidden_path not in reported_forbidden:
                    reported_forbidden.add(forbidden_path)
                    errors.append(f"forbidden path: {forbidden_path}")
                continue
            allowed_dirnames.append(dirname)
        dirnames[:] = allowed_dirnames

        for filename in filenames:
            if filename in FORBIDDEN_FILE_NAMES:
                relative = relative_current / filename if relative_current.parts else Path(filename)
                errors.append(f"forbidden file: {relative}")

    return errors


def check_secret_patterns(root: Path) -> list[str]:
    errors = []
    for path in iter_files(root, exclude_forbidden=True):
        if path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"secret-like pattern in {path.relative_to(root)}: {pattern.pattern}")
    return errors


def check_public_readme(root: Path) -> list[str]:
    readme = root / "README.md"
    if not readme.is_file():
        return ["missing README.md"]

    text = readme.read_text(encoding="utf-8")
    errors = []
    if "# Meridian" not in text:
        errors.append("README.md does not use the Meridian codename heading")

    for term in ["Warehouse Control Desk", "СКЛАД_лайт", "Yandex.Disk"]:
        if term in text:
            errors.append(f"README.md contains non-public term: {term}")

    return errors


def check_forbidden_public_text(root: Path) -> list[str]:
    errors = []
    for path in iter_files(root, exclude_forbidden=True):
        if path.relative_to(root).as_posix() == "scripts/check_public_readiness.py":
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in sorted(FORBIDDEN_PUBLIC_TEXT):
            if term in text:
                errors.append(f"forbidden public text in {path.relative_to(root)}: {term}")
    return errors


def run_checks(root: Path) -> list[str]:
    errors = []
    errors.extend(check_required_files(root))
    errors.extend(check_forbidden_paths(root))
    errors.extend(check_secret_patterns(root))
    errors.extend(check_public_readme(root))
    errors.extend(check_forbidden_public_text(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check public repository hygiene.")
    parser.add_argument("--target", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    root = args.target.expanduser().resolve()
    if not root.exists():
        print(f"Public repository does not exist: {root}", file=sys.stderr)
        return 1

    errors = run_checks(root)
    if errors:
        print("Public readiness check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Public readiness check passed for {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
