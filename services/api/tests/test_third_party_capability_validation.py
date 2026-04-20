from __future__ import annotations

from datetime import date
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


def _load_validator_module():
    required_rel = Path("scripts/ci/validate_third_party_capabilities.py")
    repo_root = _resolve_repo_root(required_rel)
    script_path = repo_root / required_rel
    spec = spec_from_file_location("validate_third_party_capabilities", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ClaimSource.model_rebuild()
    module.ClaimVerification.model_rebuild()
    module.CapabilityClaim.model_rebuild()
    module.CapabilityRegistry.model_rebuild()
    return module


def test_adopt_decision_requires_poc_and_adr(tmp_path):
    mod = _load_validator_module()
    registry = mod.CapabilityRegistry.model_validate(
        {
            "version": "1.0",
            "claims": [
                {
                    "claim_id": "TP-2026-001",
                    "provider": "example-vendor",
                    "capability": "example capability",
                    "decision": "adopt",
                    "status": "validated",
                    "source": {
                        "url": "https://example.com/docs",
                        "title": "Example docs",
                        "published_on": "2025-01-01",
                        "accessed_on": "2026-01-01",
                    },
                    "verification": {
                        "method": "docs",
                        "verified_on": "2026-01-01",
                        "owner": "platform",
                    },
                    "review_due_on": "2026-12-31",
                    "adr_refs": [],
                }
            ],
        }
    )
    errors = mod._validate_business_rules(registry, tmp_path)
    assert any("require POC evidence" in err for err in errors)
    assert any("require verification.poc_ref" in err for err in errors)
    assert any("require at least one ADR reference" in err for err in errors)


def test_defer_docs_only_claim_passes_with_valid_dates(tmp_path):
    mod = _load_validator_module()
    next_year = date.today().replace(year=date.today().year + 1).isoformat()
    registry = mod.CapabilityRegistry.model_validate(
        {
            "version": "1.0",
            "claims": [
                {
                    "claim_id": "TP-2026-002",
                    "provider": "example-vendor",
                    "capability": "example capability",
                    "decision": "defer",
                    "status": "monitoring",
                    "source": {
                        "url": "https://example.com/docs",
                        "title": "Example docs",
                        "published_on": "2025-01-01",
                        "accessed_on": "2026-01-01",
                    },
                    "verification": {
                        "method": "docs",
                        "verified_on": "2026-01-01",
                        "owner": "platform",
                    },
                    "review_due_on": next_year,
                    "adr_refs": [],
                }
            ],
        }
    )
    errors = mod._validate_business_rules(registry, tmp_path)
    assert errors == []
