#!/usr/bin/env python3
"""Enforce audit-log write conventions for API request handlers.

Rules:
1) `write_audit_event` must never be deferred via `BackgroundTasks.add_task(...)`.
2) In mutating handlers, `db.commit()` must not occur before `write_audit_event(...)`.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys


_MUTATION_METHODS = {"add", "delete", "execute", "merge", "commit"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    code: str
    message: str


def _is_write_audit_event_reference(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "write_audit_event"
    if isinstance(node, ast.Attribute):
        return node.attr == "write_audit_event"
    return False


def _is_write_audit_event_call(node: ast.Call) -> bool:
    return _is_write_audit_event_reference(node.func)


def _called_attr_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_background_task_audit_schedule(node: ast.Call) -> bool:
    if _called_attr_name(node) != "add_task":
        return False
    for arg in node.args:
        if _is_write_audit_event_reference(arg):
            return True
    for kw in node.keywords:
        if kw.value is not None and _is_write_audit_event_reference(kw.value):
            return True
    return False


def _iter_function_nodes(tree: ast.AST) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    nodes: list[ast.AsyncFunctionDef | ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            nodes.append(node)
    return nodes


def check_source(path: Path, source: str) -> list[Violation]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path=path,
                line=exc.lineno or 1,
                code="AUD000",
                message=f"Unable to parse file: {exc.msg}",
            )
        ]

    violations: list[Violation] = []
    for func in _iter_function_nodes(tree):
        audit_call_lines: list[int] = []
        commit_lines: list[int] = []
        mutation_lines: list[int] = []
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            if _is_write_audit_event_call(node):
                audit_call_lines.append(node.lineno)
            if _is_background_task_audit_schedule(node):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        code="AUD001",
                        message=(
                            "write_audit_event must not be deferred via "
                            "BackgroundTasks.add_task"
                        ),
                    )
                )

            method_name = _called_attr_name(node)
            if method_name is None:
                continue
            if method_name == "commit":
                commit_lines.append(node.lineno)
            if method_name in _MUTATION_METHODS:
                mutation_lines.append(node.lineno)

        if not audit_call_lines or not commit_lines or not mutation_lines:
            continue

        first_audit = min(audit_call_lines)
        early_commits = [line for line in commit_lines if line < first_audit]
        if early_commits:
            violations.append(
                Violation(
                    path=path,
                    line=min(early_commits),
                    code="AUD002",
                    message=(
                        "db.commit() occurs before write_audit_event() in a mutating "
                        "handler; audit writes must happen in the same transaction "
                        "before commit"
                    ),
                )
            )

    return violations


def check_paths(paths: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        violations.extend(check_source(path, source))
    return violations


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="services/api/botcheck_api",
        help="Root directory to scan for Python files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(args.root)
    if not root.exists():
        print(f"AUD000 {root}:1 root path does not exist", file=sys.stderr)
        return 2

    violations = check_paths(_iter_python_files(root))
    if not violations:
        print("audit write convention check passed")
        return 0

    for violation in violations:
        print(
            f"{violation.code} {violation.path}:{violation.line} {violation.message}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
