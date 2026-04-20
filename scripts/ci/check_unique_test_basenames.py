#!/usr/bin/env python3
"""Fail CI when duplicate Python test basenames exist across the workspace."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SCAN_ROOTS = ("services", "packages")


def iter_python_test_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def find_duplicate_test_basenames(paths: Iterable[Path]) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        by_name[path.name].append(path)
    return {name: sorted(items) for name, items in by_name.items() if len(items) > 1}


def _resolve_repo_root() -> Path:
    env_root = os.getenv("BOTCHECK_REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[2]


def main() -> int:
    repo_root = _resolve_repo_root()
    test_files = iter_python_test_files(repo_root)
    duplicates = find_duplicate_test_basenames(test_files)
    if not duplicates:
        print(f"OK: {len(test_files)} Python test files scanned, no duplicate basenames found")
        return 0

    print("ERROR: Duplicate Python test basenames found:")
    for basename in sorted(duplicates):
        print(f"  - {basename}")
        for path in duplicates[basename]:
            print(f"      {path.relative_to(repo_root)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
