import hashlib
from datetime import UTC, datetime

import yaml
from botcheck_scenarios import ScenarioDefinition
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..exceptions import (
    AI_PERSONA_NOT_FOUND,
    ApiProblem,
    AI_SCENARIO_NOT_FOUND,
    AI_SCENARIO_RECORD_NOT_FOUND,
    AI_SCENARIOS_DISABLED,
    PREVIEW_RATE_LIMITED,
    SCENARIO_NOT_FOUND,
)
from ..audit import write_audit_event
from ..auth.core import get_tenant_row
from ..admin.quota_service import assert_tenant_quota_available
from ..auth import (
    UserContext,
    get_service_caller,
    require_any_valid_token,
    require_editor,
    require_viewer,
)
from ..config import settings
from ..database import get_db
from ..retention import download_artifact_bytes, upload_artifact_bytes
from .ai_routes import router as ai_router
from .cache_routes import router as cache_router
from .generate_routes import router as generate_router
from .schemas import (
    AIPersonaDetailResponse,
    AIPersonaSummaryResponse,
    AIPersonaUpsertRequest,
    AIScenarioDetailResponse,
    AIScenarioRecordResponse,
    AIScenarioRecordUpsertRequest,
    AIScenarioSummaryResponse,
    AIScenarioUpsertRequest,
    ScenarioCacheRebuildResponse,
    ScenarioCacheStateResponse,
    ScenarioCacheSyncRequest,
    ScenarioCacheSyncResponse,
    ScenarioCacheTurnState,
    ScenarioCreate,
    ScenarioResponse,
    ScenarioSourceResponse,
    ScenarioValidationError,
    ScenarioValidationResult,
)
from .store_service import (
    delete_scenario as delete_scenario_record,
    get_scenario as get_stored_scenario,
    get_scenario_yaml,
    has_schedules_for_scenario,
    list_scenarios as list_stored_scenarios,
    store_scenario as store_scenario_record,
    sync_scenario_cache_status,
)
from ..scenarios.service import (
    assert_scenario_speech_config_available,
    ascii_path_summary,
    cycle_warnings,
    enqueue_purge_cache_job,
    enqueue_warm_cache_job,
    inspect_scenario_tts_cache,
    is_s3_not_found_error,
    parse_scenario_yaml,
    preview_rate_limit_key,
    require_preview_role,
    require_tts_cache_enabled,
    synthesize_preview_wav,
)

router = APIRouter()


def _require_ai_scenarios_enabled() -> None:
    if not settings.feature_ai_scenarios_enabled:
        raise ApiProblem(
            status=503,
            error_code=AI_SCENARIOS_DISABLED,
            detail="AI scenarios are disabled",
        )


def _lookup_problem_for_detail(detail: str) -> ApiProblem:
    normalized = detail.strip().lower()
    if normalized == "ai persona not found":
        return ApiProblem(status=404, error_code=AI_PERSONA_NOT_FOUND, detail=detail)
    if normalized == "ai scenario not found":
        return ApiProblem(status=404, error_code=AI_SCENARIO_NOT_FOUND, detail=detail)
    if normalized == "ai scenario record not found":
        return ApiProblem(status=404, error_code=AI_SCENARIO_RECORD_NOT_FOUND, detail=detail)
    return ApiProblem(status=404, error_code=SCENARIO_NOT_FOUND, detail=detail)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[ScenarioResponse])
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    return [
        ScenarioResponse(
            id=stored.scenario.id,
            name=stored.scenario.name,
            namespace=stored.namespace,
            type=stored.scenario.type.value,
            scenario_kind=stored.scenario_kind,  # type: ignore[arg-type]
            description=stored.scenario.description,
            version_hash=stored.version_hash,
            cache_status=stored.cache_status,
            cache_updated_at=stored.cache_updated_at,
            tags=stored.scenario.tags,
            turns=len(stored.scenario.turns),
            created_at=stored.created_at,
        )
        for stored in await list_stored_scenarios(db, user.tenant_id)
    ]


@router.post("/", response_model=ScenarioResponse, status_code=201)
async def create_scenario(
    body: ScenarioCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
    await assert_tenant_quota_available(
        db,
        tenant=tenant,
        tenant_id=user.tenant_id,
        quota_name="max_scenarios",
    )
    scenario = parse_scenario_yaml(body.yaml_content)
    await assert_scenario_speech_config_available(
        db,
        tenant_id=user.tenant_id,
        scenario=scenario,
        status_code=422,
    )

    version_hash = hashlib.sha256(body.yaml_content.encode()).hexdigest()[:16]
    try:
        stored_row = await store_scenario_record(
            db,
            scenario,
            version_hash,
            body.yaml_content,
            user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="scenario.upsert",
        resource_type="scenario",
        resource_id=scenario.id,
        detail={"version_hash": version_hash, "name": scenario.name},
    )
    await db.commit()

    cache_status = "cold"
    cache_updated_at: datetime | None = None
    if settings.tts_cache_enabled and await enqueue_warm_cache_job(
        request,
        scenario=scenario,
        tenant_id=user.tenant_id,
        version_hash=version_hash,
    ):
        sync_result = await sync_scenario_cache_status(
            db,
            scenario_id=scenario.id,
            tenant_id=user.tenant_id,
            scenario_version_hash=version_hash,
            cache_status="warming",
        )
        if sync_result.applied:
            cache_status = "warming"
            cache_updated_at = datetime.now(UTC)
            await db.commit()

    return ScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        namespace=stored_row.namespace,
        type=scenario.type.value,
        scenario_kind="graph",
        description=scenario.description,
        version_hash=version_hash,
        cache_status=cache_status,
        cache_updated_at=cache_updated_at,
        tags=scenario.tags,
        turns=len(scenario.turns),
    )


@router.get("/{scenario_id}/source", response_model=ScenarioSourceResponse)
async def get_scenario_source(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    yaml_content = await get_scenario_yaml(db, scenario_id, user.tenant_id)
    if yaml_content is None:
        raise ApiProblem(
            status=404,
            error_code=SCENARIO_NOT_FOUND,
            detail="Scenario not found",
        )
    return ScenarioSourceResponse(scenario_id=scenario_id, yaml_content=yaml_content)


@router.put("/{scenario_id}", response_model=ScenarioResponse)
async def update_scenario(
    scenario_id: str,
    body: ScenarioCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    scenario = parse_scenario_yaml(body.yaml_content)
    await assert_scenario_speech_config_available(
        db,
        tenant_id=user.tenant_id,
        scenario=scenario,
        status_code=422,
    )
    if scenario.id != scenario_id:
        raise HTTPException(
            status_code=422,
            detail=f"Scenario ID mismatch: path={scenario_id!r} payload={scenario.id!r}",
        )

    version_hash = hashlib.sha256(body.yaml_content.encode()).hexdigest()[:16]
    try:
        stored_row = await store_scenario_record(
            db,
            scenario,
            version_hash,
            body.yaml_content,
            user.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="scenario.update",
        resource_type="scenario",
        resource_id=scenario.id,
        detail={"version_hash": version_hash, "name": scenario.name},
    )
    await db.commit()

    cache_status = "cold"
    cache_updated_at: datetime | None = None
    if settings.tts_cache_enabled and await enqueue_warm_cache_job(
        request,
        scenario=scenario,
        tenant_id=user.tenant_id,
        version_hash=version_hash,
    ):
        sync_result = await sync_scenario_cache_status(
            db,
            scenario_id=scenario.id,
            tenant_id=user.tenant_id,
            scenario_version_hash=version_hash,
            cache_status="warming",
        )
        if sync_result.applied:
            cache_status = "warming"
            cache_updated_at = datetime.now(UTC)
            await db.commit()

    return ScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        namespace=stored_row.namespace,
        type=scenario.type.value,
        scenario_kind="graph",
        description=scenario.description,
        version_hash=version_hash,
        cache_status=cache_status,
        cache_updated_at=cache_updated_at,
        tags=scenario.tags,
        turns=len(scenario.turns),
    )


@router.delete("/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    if await has_schedules_for_scenario(db, scenario_id, user.tenant_id):
        raise HTTPException(
            status_code=409,
            detail="Scenario is referenced by one or more schedules",
        )

    scenario_data = await get_stored_scenario(db, scenario_id, user.tenant_id)
    if scenario_data is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario, _ = scenario_data
    turn_ids = [
        turn.id
        for turn in scenario.turns
        if turn.kind == "harness_prompt" and bool(turn.content.text)
    ]

    deleted = await delete_scenario_record(db, scenario_id, user.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        actor_type="user",
        action="scenario.delete",
        resource_type="scenario",
        resource_id=scenario_id,
        detail={},
    )
    await db.commit()

    # Best effort: scenario delete should not fail if cache purge queue is unavailable.
    # Purge is intentionally independent of the cache feature flag so stale objects
    # can be cleaned up even when warming/read-through are disabled.
    await enqueue_purge_cache_job(
        request,
        scenario_id=scenario_id,
        tenant_id=user.tenant_id,
        turn_ids=turn_ids,
    )


router.include_router(cache_router)
router.include_router(ai_router)


@router.post("/validate", response_model=ScenarioValidationResult)
async def validate_scenario(
    body: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    """Validate a scenario YAML without persisting it."""
    try:
        raw = yaml.safe_load(body.yaml_content)
    except yaml.YAMLError as exc:
        return ScenarioValidationResult(
            valid=False,
            errors=[ScenarioValidationError(field="$", message=f"Invalid YAML: {exc}")],
        )

    if not isinstance(raw, dict):
        return ScenarioValidationResult(
            valid=False,
            errors=[
                ScenarioValidationError(
                    field="$",
                    message="Scenario must be a YAML object with top-level fields",
                )
            ],
        )

    try:
        scenario = ScenarioDefinition.model_validate(raw)
    except PydanticValidationError as exc:
        errors = [
            ScenarioValidationError(
                field=".".join(str(part) for part in err.get("loc", ())) or "$",
                message=err.get("msg", "Invalid value"),
            )
            for err in exc.errors()
        ]
        return ScenarioValidationResult(valid=False, errors=errors)
    try:
        await assert_scenario_speech_config_available(
            db,
            tenant_id=user.tenant_id,
            scenario=scenario,
            status_code=422,
        )
    except ApiProblem as exc:
        return ScenarioValidationResult(
            valid=False,
            errors=[
                ScenarioValidationError(
                    field=(
                        "config.tts_voice"
                        if exc.error_code and exc.error_code.startswith("tts_")
                        else "config.stt_provider"
                    ),
                    message=exc.detail,
                )
            ],
        )
    except ValueError as exc:
        return ScenarioValidationResult(
            valid=False,
            errors=[
                ScenarioValidationError(
                    field=(
                        "config.tts_voice"
                        if "tts_voice" in str(exc).lower()
                        else "config.stt_model"
                    ),
                    message=str(exc),
                )
            ],
        )

    warnings = cycle_warnings(scenario)
    return ScenarioValidationResult(
        valid=True,
        errors=[],
        warnings=warnings,
        scenario_id=scenario.id,
        turns=len(scenario.turns),
        path_summary=ascii_path_summary(scenario),
    )


router.include_router(generate_router)


@router.get("/{scenario_id}", response_model=ScenarioDefinition)
async def get_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_any_valid_token),
) -> ScenarioDefinition:
    """
    Return the full ScenarioDefinition as JSON.
    Returns the complete model (not just the summary) so the agent and judge
    workers can reconstruct a ScenarioDefinition via model_validate(resp.json()).
    Accepts both user JWTs (web UI) and internal service tokens (harness, judge).
    """
    result = await get_stored_scenario(db, scenario_id, settings.tenant_id)
    if result is None:
        raise ApiProblem(
            status=404,
            error_code=SCENARIO_NOT_FOUND,
            detail="Scenario not found",
        )
    scenario, _ = result
    return scenario.model_dump(mode="json")
