"""Scoring rubric resolution tests for Scenario DSL models."""

from botcheck_scenarios import (
    DimensionRubric,
    ScenarioType,
    ScoringDimension,
    resolve_rubric,
)


class TestDslScoring:

    def test_default_adversarial_rubric(self):
        rubric = resolve_rubric(ScenarioType.ADVERSARIAL, [])
        dims = {r.dimension for r in rubric}
        assert ScoringDimension.JAILBREAK in dims
        assert ScoringDimension.DISCLOSURE in dims
        assert ScoringDimension.ROLE_INTEGRITY in dims

    def test_override_wins(self):
        override = DimensionRubric(
            dimension=ScoringDimension.JAILBREAK,
            weight=0.9,
            threshold=0.99,
            gate=True,
        )
        rubric = resolve_rubric(ScenarioType.ADVERSARIAL, [override])
        jailbreak = next(r for r in rubric if r.dimension == ScoringDimension.JAILBREAK)
        assert jailbreak.threshold == 0.99

    def test_gate_dimensions(self):
        rubric = resolve_rubric(ScenarioType.ADVERSARIAL, [])
        gate_dims = [r for r in rubric if r.gate]
        assert len(gate_dims) >= 1

    def test_custom_prompt_blank_string_normalizes_to_none(self):
        rubric = DimensionRubric(
            dimension=ScoringDimension.POLICY,
            weight=0.5,
            threshold=0.9,
            gate=True,
            custom_prompt="   ",
        )
        assert rubric.custom_prompt is None

    def test_custom_prompt_preserves_non_blank_text(self):
        rubric = DimensionRubric(
            dimension=ScoringDimension.ROUTING,
            weight=0.5,
            threshold=0.9,
            gate=True,
            custom_prompt="Route only to oncology queue family.",
        )
        assert rubric.custom_prompt == "Route only to oncology queue family."
