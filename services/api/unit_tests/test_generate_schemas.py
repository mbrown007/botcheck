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


def _load_generator_module():
    required_rel = Path("scripts/generate_schemas.py")
    repo_root = _resolve_repo_root(required_rel)
    script_path = repo_root / required_rel
    spec = spec_from_file_location("generate_schemas", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generate_schemas_writes_expected_files(tmp_path: Path) -> None:
    mod = _load_generator_module()

    written = mod.generate_schemas(tmp_path)

    assert {path.name for path in written} == {
        "README.md",
        "ai-scenario-upsert-request.json",
        "scenario-config.json",
        "scenario-definition.json",
        "speech-capabilities.json",
    }

    scenario_definition = (tmp_path / "scenario-definition.json").read_text(encoding="utf-8")
    assert '"title": "ScenarioDefinition"' in scenario_definition
    assert '"turns"' in scenario_definition
    assert '"config"' in scenario_definition
    assert '"custom_prompt"' in scenario_definition

    scenario_config = (tmp_path / "scenario-config.json").read_text(encoding="utf-8")
    assert '"title": "ScenarioConfig"' in scenario_config
    assert '"tts_voice"' in scenario_config
    assert '"stt_provider"' in scenario_config

    speech_capabilities = (tmp_path / "speech-capabilities.json").read_text(encoding="utf-8")
    assert '"title": "SpeechCapabilities"' in speech_capabilities
    assert '"tts"' in speech_capabilities
    assert '"stt"' in speech_capabilities

    ai_upsert = (tmp_path / "ai-scenario-upsert-request.json").read_text(encoding="utf-8")
    assert '"title": "AIScenarioUpsertRequest"' in ai_upsert
    assert '"config"' in ai_upsert

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "`scenario-definition.json`" in readme
    assert "`botcheck_scenarios.dsl.ScenarioDefinition`" in readme
    assert "freeform object" in readme


def test_generate_schemas_removes_stale_json_files(tmp_path: Path) -> None:
    mod = _load_generator_module()
    stale = tmp_path / "stale-schema.json"
    stale.write_text("{}", encoding="utf-8")

    mod.generate_schemas(tmp_path)

    assert not stale.exists()


def test_committed_scenario_definition_matches_generator_output(tmp_path: Path) -> None:
    mod = _load_generator_module()
    repo_root = _resolve_repo_root(Path("scripts/generate_schemas.py"))

    mod.generate_schemas(tmp_path)

    generated = (tmp_path / "scenario-definition.json").read_text(encoding="utf-8")
    committed_root = (repo_root / "schemas" / "scenario-definition.json").read_text(
        encoding="utf-8"
    )
    committed_web = (
        repo_root / "web" / "src" / "lib" / "generated-schemas" / "scenario-definition.json"
    ).read_text(encoding="utf-8")

    assert generated == committed_root
    assert generated == committed_web
