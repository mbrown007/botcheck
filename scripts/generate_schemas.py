from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from botcheck_scenarios import ScenarioConfig, ScenarioDefinition, SpeechCapabilities
from botcheck_api.scenarios.schemas import AIScenarioUpsertRequest


@dataclass(frozen=True)
class SchemaTarget:
    filename: str
    model: Type[BaseModel]
    source: str
    description: str
    notes: str = ""


SCHEMA_TARGETS: tuple[SchemaTarget, ...] = (
    SchemaTarget(
        filename="scenario-definition.json",
        model=ScenarioDefinition,
        source="botcheck_scenarios.dsl.ScenarioDefinition",
        description="Root BotCheck graph-scenario DSL model",
        notes="Includes nested persona, runtime config, turns, and scoring contracts.",
    ),
    SchemaTarget(
        filename="scenario-config.json",
        model=ScenarioConfig,
        source="botcheck_scenarios.turns.ScenarioConfig",
        description="Reusable runtime configuration embedded in scenario definitions",
        notes="Covers timing, TTS, and STT fields used by graph scenarios.",
    ),
    SchemaTarget(
        filename="speech-capabilities.json",
        model=SpeechCapabilities,
        source="botcheck_scenarios.speech.SpeechCapabilities",
        description="Shared `/features` speech capability contract",
        notes="Captures the provider capability surface exposed to Builder and AI Scenarios.",
    ),
    SchemaTarget(
        filename="ai-scenario-upsert-request.json",
        model=AIScenarioUpsertRequest,
        source="botcheck_api.scenarios.schemas.AIScenarioUpsertRequest",
        description="Current AI-scenario authoring API contract",
        notes=(
            "The `config` field remains a freeform object in this slice because AI runtime "
            "config does not yet have a dedicated shared Pydantic model."
        ),
    ),
)


def render_schema(model: Type[BaseModel]) -> dict:
    return model.model_json_schema()


def write_schema_file(target: SchemaTarget, output_dir: Path) -> Path:
    path = output_dir / target.filename
    payload = json.dumps(render_schema(target.model), indent=2, sort_keys=True)
    path.write_text(f"{payload}\n", encoding="utf-8")
    return path


def write_readme(output_dir: Path) -> Path:
    lines = [
        "# Generated Schemas",
        "",
        "These JSON Schema artifacts are generated from canonical Pydantic models.",
        "Regenerate them with:",
        "",
        "```bash",
        "uv run python scripts/generate_schemas.py",
        "```",
        "",
        "| File | Canonical model | Purpose | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for target in SCHEMA_TARGETS:
        lines.append(
            f"| `{target.filename}` | `{target.source}` | {target.description} | {target.notes or '—'} |"
        )
    lines.extend(
        [
            "",
            "Generated files in this directory should not be edited by hand.",
        ]
    )
    path = output_dir / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def remove_stale_schema_files(output_dir: Path) -> None:
    expected = {target.filename for target in SCHEMA_TARGETS}
    for path in output_dir.glob("*.json"):
        if path.name not in expected:
            path.unlink()


def generate_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_schema_files(output_dir)
    written = [write_schema_file(target, output_dir) for target in SCHEMA_TARGETS]
    written.append(write_readme(output_dir))
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate JSON Schema artifacts from canonical models.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("schemas"),
        help="Directory to write generated schema artifacts into",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    written = generate_schemas(args.output_dir)
    for path in written:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
