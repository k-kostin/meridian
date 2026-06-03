#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DJANGO_PATH_PREFIXES = {"warehouse_app", "config", "templates"}
DOC_SUFFIXES = {".md", ".txt", ".rst"}


def normalize_project_path(raw_path: str) -> str:
    raw = Path(raw_path)
    candidate = raw if raw.is_absolute() else ROOT / raw
    resolved = candidate.resolve()

    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"path is outside project root: {raw_path}") from exc

    return relative.as_posix()


def is_django_impacting(path: str) -> bool:
    parts = Path(path).parts
    if not parts:
        return False
    if path == "manage.py":
        return True
    if parts[0] in DJANGO_PATH_PREFIXES:
        return True
    return False


def is_docs_only(path: str) -> bool:
    rel = Path(path)
    if rel.suffix.lower() in DOC_SUFFIXES:
        return True
    if rel.parts and rel.parts[0] == "docs":
        return True
    return False


def command_plan(paths: list[str], *, python_cmd: str = sys.executable, full: bool = False) -> list[list[str]]:
    if full:
        return [
            [python_cmd, "manage.py", "check"],
            [python_cmd, "manage.py", "test"],
        ]

    if not paths:
        return [[python_cmd, "manage.py", "check"]]

    normalized = [normalize_project_path(path) for path in paths]
    commands: list[list[str]] = []

    python_files = [path for path in normalized if Path(path).suffix == ".py"]
    if python_files:
        commands.append([python_cmd, "-m", "py_compile", *python_files])

    django_impacted = any(is_django_impacting(path) for path in normalized)
    non_docs_change = any(not is_docs_only(path) for path in normalized)

    if django_impacted:
        commands.append([python_cmd, "manage.py", "check"])

    if django_impacted and non_docs_change:
        commands.append([python_cmd, "manage.py", "test"])

    return commands


def run_commands(commands: list[list[str]], *, dry_run: bool) -> int:
    if not commands:
        print("No guardrail commands needed for docs-only changes.")
        return 0

    for command in commands:
        print("+ " + " ".join(command))
        if dry_run:
            continue
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode != 0:
            return completed.returncode

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run fast guardrail checks for explicitly changed warehouse project files.",
    )
    parser.add_argument("paths", nargs="*", help="Changed file paths relative to project root.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected commands without running them.")
    parser.add_argument("--full", action="store_true", help="Run the baseline Django check and test suite.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for commands.")
    args = parser.parse_args(argv)

    try:
        commands = command_plan(args.paths, python_cmd=args.python, full=args.full)
    except ValueError as exc:
        print(f"check_changed: {exc}", file=sys.stderr)
        return 2

    return run_commands(commands, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
