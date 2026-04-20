#!/usr/bin/env python3
"""Validate scheduled regression pack membership against example scenarios."""

from __future__ import annotations

from pathlib import Path

import yaml
from botcheck_scenarios import ScenarioType, load_scenarios_dir


PACK_PATH = Path("scenarios/packs/scheduled-production-regression.yaml")
EXAMPLES_DIR = Path("scenarios/examples")
INVERSE_SCENARIO_ID = "inverse-jailbreak-harness-hardening"


def main() -> int:
    if not PACK_PATH.exists():
        raise SystemExit(f"Missing regression pack file: {PACK_PATH}")

    loaded = yaml.safe_load(PACK_PATH.read_text(encoding="utf-8")) or {}
    scenario_ids = loaded.get("scenarios")
    if not isinstance(scenario_ids, list) or not scenario_ids:
        raise SystemExit(f"Pack {PACK_PATH} must define a non-empty 'scenarios' list")

    scenarios = {s.id: s for s in load_scenarios_dir(str(EXAMPLES_DIR))}
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in scenarios]
    if missing:
        raise SystemExit(
            "Regression pack references unknown scenarios: " + ", ".join(sorted(missing))
        )

    if INVERSE_SCENARIO_ID not in scenario_ids:
        raise SystemExit(
            f"Regression pack must include inverse scenario: {INVERSE_SCENARIO_ID}"
        )

    inverse = scenarios[INVERSE_SCENARIO_ID]
    if inverse.type != ScenarioType.ADVERSARIAL:
        raise SystemExit(
            f"Inverse scenario must be adversarial, got: {inverse.type.value}"
        )
    if "inverse-jailbreak" not in inverse.tags:
        raise SystemExit(
            "Inverse scenario must include tag 'inverse-jailbreak' for pack filtering"
        )

    print(
        "Regression pack valid:",
        loaded.get("name", "unnamed-pack"),
        f"({len(scenario_ids)} scenarios)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
