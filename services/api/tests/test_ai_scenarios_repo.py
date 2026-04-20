from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from botcheck_api import database, store_repo
from botcheck_api.config import settings
from botcheck_api.models import (
    AIPersonaRow,
    AIScenarioRecordRow,
    AIScenarioRow,
    ScenarioKind,
)


async def test_ai_repo_crud_and_tenant_scoping() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    graph_row = store_repo.create_scenario_row(
        scenario_id="scenario_graph_default_kind",
        tenant_id=settings.tenant_id,
        version_hash="hash_graph_default",
        name="Graph Default",
        namespace="catalog/golden",
        scenario_type="smoke",
        yaml_content=(
            "id: scenario_graph_default_kind\n"
            "name: Graph Default\n"
            "type: smoke\n"
            "description: test\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )
    ai_backing_row = store_repo.create_scenario_row(
        scenario_id="scenario_ai_foundation",
        tenant_id=settings.tenant_id,
        scenario_kind=ScenarioKind.AI.value,
        version_hash="hash_ai_foundation",
        name="AI Foundation",
        scenario_type="smoke",
        yaml_content=(
            "id: scenario_ai_foundation\n"
            "name: AI Foundation\n"
            "type: smoke\n"
            "description: test\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )
    primary_persona = AIPersonaRow(
        persona_id="persona_qa_1",
        tenant_id=settings.tenant_id,
        name="QA Caller",
        system_prompt="Act as a polite but persistent caller.",
        style="polite",
        voice="alloy",
        is_active=True,
    )
    same_name_other_tenant = AIPersonaRow(
        persona_id="persona_other_tenant",
        tenant_id="tenant-other",
        name="QA Caller",
        system_prompt="Other tenant persona",
        style="neutral",
        voice="alloy",
        is_active=True,
    )
    ai_scenario = AIScenarioRow(
        scenario_id="scenario_ai_foundation",
        ai_scenario_id="ai_foundation_public",
        tenant_id=settings.tenant_id,
        name="AI Foundation",
        persona_id="persona_qa_1",
        scenario_brief="Caller wants to find a property and may or may not book.",
        scenario_facts={"segment": "buyer"},
        evaluation_objective="Recommend relevant properties and only book if asked.",
        opening_strategy="wait_for_bot_greeting",
        is_active=True,
        scoring_profile="default",
        dataset_source="manual",
        config={"sample_count": 5},
    )
    record_1 = AIScenarioRecordRow(
        record_id="record_1",
        scenario_id="scenario_ai_foundation",
        tenant_id=settings.tenant_id,
        order_index=1,
        input_text="Find me a 3-bed apartment in Queens.",
        expected_output="Recommendations should be provided.",
        metadata_json={"segment": "buyer"},
        is_active=True,
    )
    record_2 = AIScenarioRecordRow(
        record_id="record_2",
        scenario_id="scenario_ai_foundation",
        tenant_id=settings.tenant_id,
        order_index=2,
        input_text="I decline to book an appointment.",
        expected_output="No booking should be made.",
        metadata_json={"segment": "buyer"},
        is_active=True,
    )

    async with factory() as session:
        await store_repo.add_scenario_row(session, graph_row)
        await store_repo.add_scenario_row(session, ai_backing_row)
        await store_repo.add_ai_persona_row(session, primary_persona)
        await store_repo.add_ai_persona_row(session, same_name_other_tenant)
        await store_repo.add_ai_scenario_row(session, ai_scenario)
        await store_repo.add_ai_scenario_record_row(session, record_1)
        await store_repo.add_ai_scenario_record_row(session, record_2)
        await session.commit()

    async with factory() as session:
        fetched_graph = await store_repo.get_scenario_row_for_tenant(
            session,
            "scenario_graph_default_kind",
            settings.tenant_id,
        )
        assert fetched_graph is not None
        assert fetched_graph.scenario_kind == ScenarioKind.GRAPH.value
        assert fetched_graph.namespace == "catalog/golden"

        fetched_ai_scenario = await store_repo.get_ai_scenario_row_for_tenant(
            session,
            scenario_id="scenario_ai_foundation",
            tenant_id=settings.tenant_id,
        )
        assert fetched_ai_scenario is not None
        assert fetched_ai_scenario.ai_scenario_id == "ai_foundation_public"
        assert fetched_ai_scenario.name == "AI Foundation"
        assert fetched_ai_scenario.persona_id == "persona_qa_1"
        assert fetched_ai_scenario.opening_strategy == "wait_for_bot_greeting"

        fetched_by_public_id = await store_repo.get_ai_scenario_row_by_ai_scenario_id_for_tenant(
            session,
            ai_scenario_id="ai_foundation_public",
            tenant_id=settings.tenant_id,
        )
        assert fetched_by_public_id is not None
        assert fetched_by_public_id.scenario_id == "scenario_ai_foundation"

        missing_cross_tenant = await store_repo.get_ai_scenario_row_for_tenant(
            session,
            scenario_id="scenario_ai_foundation",
            tenant_id="tenant-other",
        )
        assert missing_cross_tenant is None

        missing_public_cross_tenant = await store_repo.get_ai_scenario_row_by_ai_scenario_id_for_tenant(
            session,
            ai_scenario_id="ai_foundation_public",
            tenant_id="tenant-other",
        )
        assert missing_public_cross_tenant is None

        by_name = await store_repo.get_ai_persona_row_by_name_for_tenant(
            session,
            tenant_id=settings.tenant_id,
            name="QA Caller",
        )
        assert by_name is not None
        assert by_name.persona_id == "persona_qa_1"

        by_name_other_tenant = await store_repo.get_ai_persona_row_by_name_for_tenant(
            session,
            tenant_id="tenant-other",
            name="QA Caller",
        )
        assert by_name_other_tenant is not None
        assert by_name_other_tenant.persona_id == "persona_other_tenant"

        records = await store_repo.list_ai_scenario_record_rows_for_scenario_for_tenant(
            session,
            scenario_id="scenario_ai_foundation",
            tenant_id=settings.tenant_id,
        )
        assert [row.record_id for row in records] == ["record_1", "record_2"]

        assert (
            await store_repo.delete_ai_scenario_record_row_for_tenant(
                session,
                record_id="record_1",
                tenant_id="tenant-other",
            )
            is False
        )
        assert (
            await store_repo.delete_ai_scenario_record_row_for_tenant(
                session,
                record_id="record_1",
                tenant_id=settings.tenant_id,
            )
            is True
        )
        await store_repo.delete_ai_scenario_record_rows_for_scenario_for_tenant(
            session,
            scenario_id="scenario_ai_foundation",
            tenant_id=settings.tenant_id,
        )
        assert (
            await store_repo.delete_ai_scenario_row_for_tenant(
                session,
                scenario_id="scenario_ai_foundation",
                tenant_id=settings.tenant_id,
            )
            is True
        )
        assert (
            await store_repo.delete_ai_persona_row_for_tenant(
                session,
                persona_id="persona_qa_1",
                tenant_id=settings.tenant_id,
            )
            is True
        )
        await session.commit()


async def test_ai_repo_constraints_enforced() -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None

    invalid_kind = store_repo.create_scenario_row(
        scenario_id="scenario_invalid_kind",
        tenant_id=settings.tenant_id,
        scenario_kind="invalid-kind",
        version_hash="hash_invalid",
        name="Invalid Kind",
        scenario_type="smoke",
        yaml_content=(
            "id: scenario_invalid_kind\n"
            "name: Invalid Kind\n"
            "type: smoke\n"
            "description: test\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )
    persona_a = AIPersonaRow(
        persona_id="persona_dup_1",
        tenant_id=settings.tenant_id,
        name="Duplicate Name",
        system_prompt="One",
        is_active=True,
    )
    persona_b = AIPersonaRow(
        persona_id="persona_dup_2",
        tenant_id=settings.tenant_id,
        name="Duplicate Name",
        system_prompt="Two",
        is_active=True,
    )

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await store_repo.add_scenario_row(session, invalid_kind)
            await session.commit()
        await session.rollback()

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await store_repo.add_ai_persona_row(session, persona_a)
            await store_repo.add_ai_persona_row(session, persona_b)
            await session.commit()
        await session.rollback()


async def test_update_scenario_row_preserves_namespace_when_not_provided() -> None:
    row = store_repo.create_scenario_row(
        scenario_id="scenario_namespace_preserved",
        tenant_id=settings.tenant_id,
        version_hash="hash_initial",
        name="Namespace Preserved",
        namespace="billing/refunds",
        scenario_type="smoke",
        yaml_content=(
            "id: scenario_namespace_preserved\n"
            "name: Namespace Preserved\n"
            "type: smoke\n"
            "description: test\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )

    store_repo.update_scenario_row(
        row,
        version_hash="hash_updated",
        name="Namespace Preserved Updated",
        scenario_type="regression",
        yaml_content=(
            "id: scenario_namespace_preserved\n"
            "name: Namespace Preserved Updated\n"
            "type: regression\n"
            "description: updated\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )

    assert row.namespace == "billing/refunds"


async def test_update_scenario_row_can_clear_namespace_when_explicitly_set_none() -> None:
    row = store_repo.create_scenario_row(
        scenario_id="scenario_namespace_cleared",
        tenant_id=settings.tenant_id,
        version_hash="hash_initial",
        name="Namespace Cleared",
        namespace="billing/refunds",
        scenario_type="smoke",
        yaml_content=(
            "id: scenario_namespace_cleared\n"
            "name: Namespace Cleared\n"
            "type: smoke\n"
            "description: test\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )

    store_repo.update_scenario_row(
        row,
        version_hash="hash_updated",
        name="Namespace Cleared Updated",
        namespace=None,
        scenario_type="regression",
        yaml_content=(
            "id: scenario_namespace_cleared\n"
            "name: Namespace Cleared Updated\n"
            "type: regression\n"
            "description: updated\n"
            "bot:\n"
            "  protocol: mock\n"
            "  endpoint: mock://echo\n"
            "turns: []\n"
        ),
    )

    assert row.namespace is None
