from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import os
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
    required_rel = Path("scripts/ci/check_unique_test_basenames.py")
    repo_root = _resolve_repo_root(required_rel)
    script_path = repo_root / required_rel
    spec = spec_from_file_location("check_unique_test_basenames", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_find_duplicate_test_basenames_returns_empty_when_unique():
    mod = _load_checker_module()
    duplicates = mod.find_duplicate_test_basenames(
        [
            Path("services/api/tests/test_alpha.py"),
            Path("services/judge/tests/test_beta.py"),
        ]
    )
    assert duplicates == {}


def test_find_duplicate_test_basenames_returns_all_duplicate_paths():
    mod = _load_checker_module()
    duplicates = mod.find_duplicate_test_basenames(
        [
            Path("services/api/tests/test_shared.py"),
            Path("services/judge/tests/test_shared.py"),
            Path("packages/scenarios/tests/test_other.py"),
        ]
    )
    assert "test_shared.py" in duplicates
    assert duplicates["test_shared.py"] == [
        Path("services/api/tests/test_shared.py"),
        Path("services/judge/tests/test_shared.py"),
    ]
