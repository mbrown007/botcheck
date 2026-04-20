#!/usr/bin/env python3
"""Validate third-party capability verification records for architecture decisions."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

REGISTRY_PATH = Path("docs/third_party_capabilities.yaml")


class ClaimSource(BaseModel):
    url: str
    title: str
    published_on: date
    accessed_on: date

    @model_validator(mode="after")
    def validate_dates(self) -> "ClaimSource":
        if self.accessed_on < self.published_on:
            raise ValueError("source.accessed_on must be on or after source.published_on")
        return self


class ClaimVerification(BaseModel):
    method: Literal["docs", "poc", "docs+poc"]
    verified_on: date
    owner: str
    poc_ref: str | None = None
    notes: str = ""


class CapabilityClaim(BaseModel):
    claim_id: str
    provider: str
    capability: str
    decision: Literal["adopt", "defer", "reject"]
    status: Literal["validated", "monitoring", "rejected", "deprecated"] = "validated"
    source: ClaimSource
    verification: ClaimVerification
    review_due_on: date
    adr_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self) -> "CapabilityClaim":
        if self.verification.verified_on < self.source.accessed_on:
            raise ValueError("verification.verified_on must be on or after source.accessed_on")
        if self.review_due_on < self.verification.verified_on:
            raise ValueError("review_due_on must be on or after verification.verified_on")
        return self


class CapabilityRegistry(BaseModel):
    version: str
    claims: list[CapabilityClaim] = Field(default_factory=list)


def _load_registry(path: Path = REGISTRY_PATH) -> CapabilityRegistry:
    if not path.exists():
        raise SystemExit(
            f"Missing registry: {path}. Add docs/third_party_capabilities.yaml."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    return CapabilityRegistry.model_validate(raw)


def _validate_business_rules(registry: CapabilityRegistry, repo_root: Path) -> list[str]:
    errors: list[str] = []
    today = date.today()
    seen_ids: set[str] = set()
    for claim in registry.claims:
        if claim.claim_id in seen_ids:
            errors.append(f"Duplicate claim_id: {claim.claim_id}")
        seen_ids.add(claim.claim_id)

        if claim.source.published_on > today:
            errors.append(
                f"{claim.claim_id}: source.published_on is in the future ({claim.source.published_on})"
            )
        if claim.source.accessed_on > today:
            errors.append(
                f"{claim.claim_id}: source.accessed_on is in the future ({claim.source.accessed_on})"
            )
        if claim.verification.verified_on > today:
            errors.append(
                f"{claim.claim_id}: verification.verified_on is in the future ({claim.verification.verified_on})"
            )
        if claim.review_due_on < today:
            errors.append(
                f"{claim.claim_id}: review_due_on has expired ({claim.review_due_on}); re-verify capability"
            )

        if claim.decision == "adopt":
            if claim.verification.method not in {"poc", "docs+poc"}:
                errors.append(
                    f"{claim.claim_id}: adopt decisions require POC evidence (method=poc or docs+poc)"
                )
            if not claim.verification.poc_ref:
                errors.append(
                    f"{claim.claim_id}: adopt decisions require verification.poc_ref"
                )
            if not claim.adr_refs:
                errors.append(
                    f"{claim.claim_id}: adopt decisions require at least one ADR reference"
                )

        if claim.verification.poc_ref:
            poc_path = repo_root / claim.verification.poc_ref
            if not poc_path.exists():
                errors.append(
                    f"{claim.claim_id}: verification.poc_ref does not exist: {claim.verification.poc_ref}"
                )
        for adr_ref in claim.adr_refs:
            adr_path = repo_root / adr_ref
            if not adr_path.exists():
                errors.append(
                    f"{claim.claim_id}: adr_ref does not exist: {adr_ref}"
                )

    return errors


def main() -> int:
    repo_root = Path.cwd()
    registry = _load_registry()
    errors = _validate_business_rules(registry, repo_root)
    if errors:
        print("Third-party capability verification failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(
        "Third-party capability verification passed "
        f"({len(registry.claims)} claims)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
