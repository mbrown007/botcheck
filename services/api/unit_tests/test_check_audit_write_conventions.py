from __future__ import annotations

import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


def _resolve_repo_root(required_rel: Path) -> Path:
    candidates: list[Path] = []
    env_root = os.getenv("BOTCHECK_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / required_rel).exists():
            return root
    pytest.skip(
        f"Missing {required_rel} in mounted test workspace; "
        "set BOTCHECK_REPO_ROOT to the repository root to enable this test."
    )


def _load_checker_module():
    required_rel = Path("scripts/ci/check_audit_write_conventions.py")
    repo_root = _resolve_repo_root(required_rel)
    script_path = repo_root / required_rel
    spec = spec_from_file_location("check_audit_write_conventions", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_flags_background_task_audit_schedule():
    mod = _load_checker_module()
    source = """
async def bad_handler(db, background_tasks):
    background_tasks.add_task(write_audit_event, db=db, tenant_id="t")
"""
    violations = mod.check_source(Path("sample.py"), source)
    assert any(v.code == "AUD001" for v in violations)


def test_flags_commit_before_audit_in_mutating_handler():
    mod = _load_checker_module()
    source = """
async def bad_handler(db):
    db.add(object())
    await db.commit()
    await write_audit_event(
        db,
        tenant_id="t",
        actor_id="u",
        action="x",
        resource_type="r",
        resource_id="id",
    )
"""
    violations = mod.check_source(Path("sample.py"), source)
    assert any(v.code == "AUD002" for v in violations)


def test_allows_audit_before_commit():
    mod = _load_checker_module()
    source = """
async def good_handler(db):
    db.add(object())
    await write_audit_event(
        db,
        tenant_id="t",
        actor_id="u",
        action="x",
        resource_type="r",
        resource_id="id",
    )
    await db.commit()
"""
    violations = mod.check_source(Path("sample.py"), source)
    assert violations == []
