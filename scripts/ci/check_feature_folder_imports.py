from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api" / "botcheck_api"
API_TEST_ROOTS = (
    REPO_ROOT / "services" / "api" / "tests",
    REPO_ROOT / "services" / "api" / "unit_tests",
)
LEGACY_ALIAS_DIRS = (
    API_ROOT / "routers",
    API_ROOT / "services",
)
LEGACY_IMPORT_PREFIXES = (
    "botcheck_api.routers",
    "botcheck_api.services",
)
SKIP_FILES = (
    REPO_ROOT / "services" / "api" / "unit_tests" / "test_feature_folder_shims.py",
)


@dataclass(frozen=True)
class LegacyImportViolation:
    path: Path
    line: int
    imported_module: str


def should_check_path(path: Path) -> bool:
    resolved = path.resolve()
    if resolved.suffix != ".py":
        return False
    if any(resolved == skip_file.resolve() for skip_file in SKIP_FILES):
        return False
    return True


def iter_python_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.py") if should_check_path(path))
    return sorted(set(files))


def iter_runtime_python_files() -> list[Path]:
    return iter_python_files(API_ROOT)


def iter_test_python_files() -> list[Path]:
    return iter_python_files(*API_TEST_ROOTS)


def find_legacy_imports(path: Path) -> list[LegacyImportViolation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[LegacyImportViolation] = []
    resolved_path = path.resolve()
    try:
        display_path = resolved_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = resolved_path

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(LEGACY_IMPORT_PREFIXES):
                    violations.append(
                        LegacyImportViolation(
                            path=display_path,
                            line=node.lineno,
                            imported_module=alias.name,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name.startswith(LEGACY_IMPORT_PREFIXES):
                violations.append(
                    LegacyImportViolation(
                        path=display_path,
                        line=node.lineno,
                        imported_module=module_name,
                    )
                )

    return violations


def collect_violations(paths: list[Path]) -> list[LegacyImportViolation]:
    violations: list[LegacyImportViolation] = []
    for path in paths:
        violations.extend(find_legacy_imports(path))
    return violations


def existing_legacy_alias_dirs() -> list[Path]:
    return [path for path in LEGACY_ALIAS_DIRS if path.exists()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Block legacy botcheck_api.routers/services imports outside shims."
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Scan services/api/tests and services/api/unit_tests in addition to runtime code.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    legacy_dirs = existing_legacy_alias_dirs()
    if legacy_dirs:
        print("Legacy alias directories must remain deleted:")
        for path in legacy_dirs:
            print(f"  {path.relative_to(REPO_ROOT)}")
        return 1

    roots = iter_runtime_python_files()
    if args.include_tests:
        roots.extend(iter_test_python_files())
    violations = collect_violations(roots)
    if not violations:
        print("Feature-folder import guard passed.")
        return 0

    print("Legacy API imports are only allowed inside compatibility shims:")
    for violation in violations:
        print(
            f"  {violation.path}:{violation.line} imports {violation.imported_module}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
