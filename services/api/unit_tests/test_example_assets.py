from __future__ import annotations

import json
from pathlib import Path

import yaml
from botcheck_api.grai.importer import compile_promptfoo_yaml
from botcheck_api.packs.destinations import BotDestinationUpsert
from botcheck_api.packs.pack_schemas import ScenarioPackUpsert
from botcheck_api.scenarios.schemas import AIScenarioUpsertRequest
from botcheck_scenarios import load_scenario


ROOT = Path(__file__).resolve().parents[3]
GRAPH_EXAMPLES_DIR = ROOT / "scenarios" / "examples"
AI_EXAMPLES_DIR = ROOT / "scenarios" / "ai-scenarios" / "examples"
PACK_EXAMPLES_DIR = ROOT / "scenarios" / "packs" / "examples"
TRANSPORT_EXAMPLES_DIR = ROOT / "scenarios" / "transport-profiles" / "examples"
GRAI_EXAMPLES_DIR = ROOT / "grai" / "examples"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_graph_example_ids() -> set[str]:
    out: set[str] = set()
    for path in sorted(GRAPH_EXAMPLES_DIR.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scenario_id = loaded.get("id")
        if isinstance(scenario_id, str) and scenario_id.strip():
            out.add(scenario_id.strip())
    return out


def test_ai_scenario_examples_validate_and_reference_known_graph_scenarios() -> None:
    known_graph_ids = _load_graph_example_ids()

    for path in sorted(AI_EXAMPLES_DIR.glob("*.json")):
        payload = _load_json(path)
        model = AIScenarioUpsertRequest.model_validate(payload)
        assert model.scenario_id in known_graph_ids


def test_pack_examples_validate_and_reference_known_example_ids() -> None:
    known_graph_ids = _load_graph_example_ids()
    known_ai_ids = set()
    for path in sorted(AI_EXAMPLES_DIR.glob("*.json")):
        payload = AIScenarioUpsertRequest.model_validate(_load_json(path))
        assert payload.ai_scenario_id is not None
        known_ai_ids.add(payload.ai_scenario_id)

    for path in sorted(PACK_EXAMPLES_DIR.glob("*.json")):
        payload = _load_json(path)
        model = ScenarioPackUpsert.model_validate(payload)
        assert model.items
        for item in model.items:
            if item.scenario_id is not None:
                assert item.scenario_id in known_graph_ids
            if item.ai_scenario_id is not None:
                assert item.ai_scenario_id in known_ai_ids


def test_http_transport_profile_examples_validate() -> None:
    for path in sorted(TRANSPORT_EXAMPLES_DIR.glob("*.json")):
        payload = _load_json(path)
        model = BotDestinationUpsert.model_validate(payload)
        assert model.protocol.value == "http"
        assert model.direct_http_config is not None


def test_graph_examples_load_through_the_dsl(monkeypatch) -> None:
    monkeypatch.setenv("BOT_SIP_USER", "ci-bot")
    monkeypatch.setenv("SIP_PROVIDER", "ci.example.com")

    for path in sorted(GRAPH_EXAMPLES_DIR.glob("*.yaml")):
        model = load_scenario(str(path))
        assert model.id


def test_grai_examples_compile_successfully() -> None:
    for path in sorted(GRAI_EXAMPLES_DIR.glob("*.promptfoo.yaml")):
        compiled = compile_promptfoo_yaml(yaml_content=path.read_text(encoding="utf-8"))
        assert compiled.name
        assert compiled.prompts
        assert compiled.cases


def test_pack_example_readmes_and_yaml_catalog_stay_loadable() -> None:
    readme = PACK_EXAMPLES_DIR / "README.md"
    assert readme.exists()

    scheduled_pack = ROOT / "scenarios" / "packs" / "scheduled-production-regression.yaml"
    loaded = yaml.safe_load(scheduled_pack.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert isinstance(loaded.get("scenarios"), list)
