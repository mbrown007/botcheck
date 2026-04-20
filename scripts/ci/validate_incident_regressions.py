#!/usr/bin/env python3
"""Ensure closed production incidents are linked to regression fixtures."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from botcheck_scenarios import ScenarioDefinition, load_scenarios_dir

DEFAULT_REGISTRY_PATH = Path("docs/incidents/production_incidents.yaml")
DEFAULT_SCENARIOS_DIR = Path("scenarios/examples")


class IncidentRecord(BaseModel):
    id: str
    source: str = "production"
    status: str
    title: str
    regression_fixture_id: str | None = None


class IncidentRegistry(BaseModel):
    version: str
    incidents: list[IncidentRecord] = Field(default_factory=list)


def _load_registry(path: Path) -> IncidentRegistry:
    if not path.exists():
        raise SystemExit(
            f"Incident registry file not found: {path}. "
            "Create docs/incidents/production_incidents.yaml."
        )
    data = yaml.safe_load(path.read_text()) or {}
    return IncidentRegistry.model_validate(data)


def _load_scenarios(path: Path) -> dict[str, ScenarioDefinition]:
    if not path.exists():
        raise SystemExit(f"Scenario directory not found: {path}")
    scenarios = load_scenarios_dir(str(path))
    return {scenario.id: scenario for scenario in scenarios}


def validate_incident_fixtures(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    scenarios_dir: Path = DEFAULT_SCENARIOS_DIR,
) -> list[str]:
    registry = _load_registry(registry_path)
    scenarios = _load_scenarios(scenarios_dir)

    errors: list[str] = []
    seen_incidents: set[str] = set()
    for incident in registry.incidents:
        if incident.id in seen_incidents:
            errors.append(f"Duplicate incident id in registry: {incident.id}")
        seen_incidents.add(incident.id)

        if incident.source.lower() != "production":
            continue
        if incident.status.lower() != "closed":
            continue

        if not incident.regression_fixture_id:
            errors.append(
                f"Closed production incident {incident.id} is missing regression_fixture_id"
            )
            continue

        fixture = scenarios.get(incident.regression_fixture_id)
        if fixture is None:
            errors.append(
                "Closed production incident "
                f"{incident.id} references unknown scenario fixture "
                f"{incident.regression_fixture_id!r}"
            )
            continue

        incident_tag = f"incident:{incident.id.lower()}"
        if "regression-fixture" not in fixture.tags:
            errors.append(
                f"Fixture {fixture.id!r} for incident {incident.id} must include tag "
                "'regression-fixture'"
            )
        if incident_tag not in fixture.tags:
            errors.append(
                f"Fixture {fixture.id!r} for incident {incident.id} must include tag "
                f"{incident_tag!r}"
            )
    return errors


def main() -> int:
    errors = validate_incident_fixtures()
    if errors:
        print("Incident regression fixture validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Incident regression fixture validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
