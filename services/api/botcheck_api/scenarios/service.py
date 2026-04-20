"""
Scenario orchestration helpers extracted from routers/scenarios.py.

All public functions here were previously private (_-prefixed) helpers in the router
module. The leading underscore has been dropped since they are no longer private to
the router.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import aioboto3
import structlog
import yaml
from botocore.exceptions import ClientError
from botcheck_scenarios import (
    CircuitOpenError,
    CircuitTransition,
    ScenarioDefinition,
)
from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..auth import UserContext
from ..auth.security import check_login_rate_limit
from ..config import settings
from ..providers.usage_service import assert_provider_quota_available
from ..runs.provider_state import (
    KnownProviderCircuitState,
    store_provider_circuit_snapshot,
)
from ..stt_provider import assert_tenant_stt_config_available
from ..tts_provider import (
    assert_tenant_tts_voice_available,
    get_preview_tts_circuit_breaker,
    preview_provider_http_error,
    resolve_tenant_preview_tts_provider,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("botcheck.api.scenarios")
event_logger = structlog.get_logger("botcheck.api.provider_circuit")


# ---------------------------------------------------------------------------
# Validation models (shared between service and router)
# ---------------------------------------------------------------------------


class ValidationWarning(BaseModel):
    code: Literal["CYCLE_GUARANTEED_LOOP", "CYCLE_UNLIMITED_VISIT"]
    message: str
    turn_ids: list[str]


@dataclass(frozen=True)
class ScenarioCacheInspection:
    cache_status: Literal["warm", "warming", "partial", "cold"]
    cached_turns: int
    failed_turns: int
    total_harness_turns: int
    manifest_present: bool
    turn_states: list[dict[str, str | None]]


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------


def parse_scenario_yaml(yaml_content: str) -> ScenarioDefinition:
    try:
        raw = yaml.safe_load(yaml_content)
        return ScenarioDefinition.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def assert_scenario_speech_config_available(
    db: AsyncSession,
    *,
    tenant_id: str,
    scenario: ScenarioDefinition,
    status_code: int,
) -> None:
    await assert_tenant_tts_voice_available(
        db,
        tenant_id=tenant_id,
        tts_voice=scenario.config.tts_voice,
        status_code=status_code,
        runtime_scope="agent",
    )
    await assert_tenant_stt_config_available(
        db,
        tenant_id=tenant_id,
        stt_provider=scenario.config.stt_provider,
        stt_model=scenario.config.stt_model,
        status_code=status_code,
        runtime_scope="agent",
    )


# ---------------------------------------------------------------------------
# TTS cache helpers
# ---------------------------------------------------------------------------


def require_tts_cache_enabled() -> None:
    if not settings.tts_cache_enabled:
        raise HTTPException(status_code=503, detail="TTS cache is disabled")


def manifest_key(tenant_id: str, scenario_id: str) -> str:
    return f"{tenant_id}/tts-cache/{scenario_id}/manifest.json"


def derive_cache_status(*, total: int, cached: int, skipped: int, failed: int) -> str:
    if total <= 0:
        return "warm"
    if failed == 0 and (cached + skipped) == total:
        return "warm"
    if (cached + skipped) == 0:
        return "cold"
    return "partial"


def cacheable_harness_turns(scenario: ScenarioDefinition):
    return [
        turn
        for turn in scenario.turns
        if turn.kind == "harness_prompt" and bool(turn.content.text)
    ]


def scenario_requires_tts_cache_preflight(scenario: ScenarioDefinition) -> bool:
    tags = {str(tag).strip().lower() for tag in scenario.tags}
    return "smoke-test" in tags and len(cacheable_harness_turns(scenario)) > 0


async def inspect_scenario_tts_cache(
    settings_obj,
    *,
    scenario: ScenarioDefinition,
    tenant_id: str,
) -> ScenarioCacheInspection:
    turns = cacheable_harness_turns(scenario)
    if not turns:
        return ScenarioCacheInspection(
            cache_status="warm",
            cached_turns=0,
            failed_turns=0,
            total_harness_turns=0,
            manifest_present=False,
            turn_states=[],
        )

    if (
        not settings_obj.tts_cache_enabled
        or not settings_obj.s3_access_key
        or not settings_obj.s3_secret_key
    ):
        return ScenarioCacheInspection(
            cache_status="cold",
            cached_turns=0,
            failed_turns=len(turns),
            total_harness_turns=len(turns),
            manifest_present=False,
            turn_states=[
                {"turn_id": turn.id, "status": "failed", "key": None}
                for turn in turns
            ],
        )

    cached = 0
    failed = 0
    manifest_present = True
    turn_states: list[dict[str, str | None]] = []
    session = aioboto3.Session(
        aws_access_key_id=settings_obj.s3_access_key,
        aws_secret_access_key=settings_obj.s3_secret_key,
        region_name=settings_obj.s3_region,
    )
    async with session.client("s3", endpoint_url=settings_obj.s3_endpoint_url) as s3:
        manifest_s3_key = manifest_key(tenant_id, scenario.id)
        try:
            await s3.head_object(Bucket=settings_obj.s3_bucket_prefix, Key=manifest_s3_key)
        except Exception as exc:
            manifest_present = not is_s3_not_found_error(exc)

        for turn in turns:
            key = scenario.turn_cache_key(
                turn,
                tenant_id,
                pcm_format_version=settings_obj.tts_cache_pcm_format_version,
            )
            try:
                await s3.head_object(Bucket=settings_obj.s3_bucket_prefix, Key=key)
                cached += 1
                turn_states.append({"turn_id": turn.id, "status": "cached", "key": key})
            except Exception as exc:
                if not is_s3_not_found_error(exc):
                    logger.warning(
                        "TTS cache verification head_object failed for scenario=%s turn=%s key=%s",
                        scenario.id,
                        turn.id,
                        key,
                        exc_info=True,
                    )
                failed += 1
                turn_states.append({"turn_id": turn.id, "status": "failed", "key": key})

    status = derive_cache_status(
        total=len(turns),
        cached=cached,
        skipped=0,
        failed=failed,
    )
    return ScenarioCacheInspection(
        cache_status=status,  # type: ignore[arg-type]
        cached_turns=cached,
        failed_turns=failed,
        total_harness_turns=len(turns),
        manifest_present=manifest_present,
        turn_states=turn_states,
    )


def is_s3_not_found_error(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound"}
    err = getattr(exc, "response", {}).get("Error", {})
    code = str(err.get("Code", "")).strip()
    return code in {"404", "NoSuchKey", "NotFound"}


# ---------------------------------------------------------------------------
# ARQ job dispatch
# ---------------------------------------------------------------------------


async def enqueue_warm_cache_job(
    request: Request,
    *,
    scenario: ScenarioDefinition,
    tenant_id: str,
    version_hash: str,
) -> bool:
    arq_pool = getattr(request.app.state, "arq_cache_pool", None)
    if arq_pool is None:
        return False
    try:
        await arq_pool.enqueue_job(
            "warm_tts_cache",
            payload={
                "scenario_id": scenario.id,
                "tenant_id": tenant_id,
                "scenario_version_hash": version_hash,
                "scenario_payload": scenario.model_dump(mode="json"),
            },
            _queue_name="arq:cache",
        )
        return True
    except Exception:
        logger.warning(
            "Failed to enqueue warm_tts_cache for scenario %s", scenario.id, exc_info=True
        )
        return False


async def enqueue_purge_cache_job(
    request: Request,
    *,
    scenario_id: str,
    tenant_id: str,
    turn_ids: list[str],
) -> bool:
    arq_pool = getattr(request.app.state, "arq_cache_pool", None)
    if arq_pool is None:
        return False
    try:
        await arq_pool.enqueue_job(
            "purge_tts_cache",
            payload={
                "scenario_id": scenario_id,
                "tenant_id": tenant_id,
                "turn_ids": turn_ids,
            },
            _queue_name="arq:cache",
        )
        return True
    except Exception:
        logger.warning(
            "Failed to enqueue purge_tts_cache for scenario %s", scenario_id, exc_info=True
        )
        return False


# ---------------------------------------------------------------------------
# Graph algorithms (Tarjan's SCC cycle detection)
# ---------------------------------------------------------------------------


def scenario_successors(scenario: ScenarioDefinition) -> dict[str, list[str]]:
    successors: dict[str, list[str]] = {}
    turns = scenario.turns
    for idx, turn in enumerate(turns):
        next_ids: list[str] = []
        if turn.branching is not None:
            next_ids.extend(case.next for case in turn.branching.cases)
            next_ids.append(turn.branching.default)
        elif turn.next is not None:
            next_ids.append(turn.next)
        elif idx + 1 < len(turns):
            next_ids.append(turns[idx + 1].id)
        successors[turn.id] = next_ids
    return successors


def scc_cycles(scenario: ScenarioDefinition) -> list[list[str]]:
    """Return SCC cycles as ordered turn-id lists (Tarjan's algorithm)."""
    successors = scenario_successors(scenario)
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[list[str]] = []
    turn_order: dict[str, int] = {turn.id: i for i, turn in enumerate(scenario.turns)}

    def strongconnect(node_id: str) -> None:
        nonlocal index
        indexes[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)

        for next_id in successors.get(node_id, []):
            if next_id not in indexes:
                strongconnect(next_id)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[next_id])
            elif next_id in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indexes[next_id])

        if lowlinks[node_id] != indexes[node_id]:
            return

        component: list[str] = []
        while stack:
            popped = stack.pop()
            on_stack.remove(popped)
            component.append(popped)
            if popped == node_id:
                break

        if len(component) > 1:
            component.sort(key=lambda t: turn_order.get(t, 10**9))
            cycles.append(component)
            return

        single = component[0]
        if single in successors.get(single, []):
            cycles.append(component)

    for turn in scenario.turns:
        if turn.id not in indexes:
            strongconnect(turn.id)
    return cycles


def cycle_warnings(scenario: ScenarioDefinition) -> list[ValidationWarning]:
    by_id = {turn.id: turn for turn in scenario.turns}
    warnings: list[ValidationWarning] = []

    for cycle in scc_cycles(scenario):
        cycle_turns = [by_id[turn_id] for turn_id in cycle if turn_id in by_id]
        if not cycle_turns:
            continue

        if all(turn.max_visits == 1 for turn in cycle_turns):
            warnings.append(
                ValidationWarning(
                    code="CYCLE_GUARANTEED_LOOP",
                    message=(
                        "Cycle with all max_visits=1 detected; traversal will fail on the "
                        "second visit of a cycle node."
                    ),
                    turn_ids=cycle,
                )
            )
        if any(turn.max_visits == 0 for turn in cycle_turns):
            warnings.append(
                ValidationWarning(
                    code="CYCLE_UNLIMITED_VISIT",
                    message=(
                        "Cycle containing max_visits=0 detected; traversal is unbounded and "
                        "relies on max_total_turns cap."
                    ),
                    turn_ids=cycle,
                )
            )
    return warnings


def ascii_path_summary(scenario: ScenarioDefinition) -> str:
    lines = [
        f"Scenario: {scenario.id} ({scenario.type.value})",
        "Path Graph:",
    ]

    for idx, turn in enumerate(scenario.turns):
        visit_cap = "∞" if turn.max_visits == 0 else str(turn.max_visits)
        lines.append(
            f"[{idx + 1:02d}] {turn.id} [{turn.kind}] max_visits={visit_cap}"
        )

        if turn.branching is not None:
            for case in turn.branching.cases:
                lines.append(f"   ? {case.condition} -> {case.next}")
            lines.append(f"   ? default -> {turn.branching.default}")
            continue

        if turn.next is not None:
            lines.append(f"   -> {turn.next}")
            continue

        if idx + 1 < len(scenario.turns):
            lines.append(f"   -> {scenario.turns[idx + 1].id} (implicit)")
            continue

        lines.append("   -> END")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TTS preview helpers
# ---------------------------------------------------------------------------


def _record_preview_tts_transition(*, provider: str, transition: CircuitTransition) -> None:
    api_metrics.PROVIDER_CIRCUIT_TRANSITIONS_TOTAL.labels(
        provider=provider,
        service="tts",
        component="api_preview",
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
    ).inc()
    event_logger.warning(
        "provider_circuit_transition",
        provider=provider,
        service="tts",
        component="api_preview",
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
        reason=transition.reason,
    )


def _record_preview_tts_reject(*, provider: str, state) -> None:
    api_metrics.PROVIDER_CIRCUIT_REJECTIONS_TOTAL.labels(
        provider=provider,
        service="tts",
        component="api_preview",
    ).inc()
    event_logger.warning(
        "provider_circuit_rejected",
        provider=provider,
        service="tts",
        component="api_preview",
        state=getattr(state, "value", str(state)),
    )


def _known_provider_state(value: str) -> KnownProviderCircuitState | None:
    normalized = value.strip().lower()
    if normalized == "open":
        return "open"
    if normalized == "half_open":
        return "half_open"
    if normalized == "closed":
        return "closed"
    return None


def _schedule_preview_circuit_snapshot_write(
    *,
    provider: str,
    redis_pool: object | None,
    state: KnownProviderCircuitState,
) -> None:
    task = asyncio.create_task(
        store_provider_circuit_snapshot(
            redis_pool,
            source="api",
            provider=provider,
            service="tts",
            component="api_preview",
            state=state,
            observed_at=datetime.now(UTC),
            ttl_s=settings.provider_circuit_snapshot_ttl_s,
        )
    )

    def _on_done(done: asyncio.Task[bool]) -> None:
        try:
            stored = done.result()
        except Exception:
            logger.warning(
                "provider_circuit_snapshot_publish_failed source=api provider=%s service=tts component=api_preview",
                provider,
                exc_info=True,
            )
            return
        if not stored:
            logger.warning(
                "provider_circuit_snapshot_not_stored source=api provider=%s service=tts component=api_preview",
                provider,
            )

    task.add_done_callback(_on_done)


def require_preview_role(user: UserContext) -> None:
    if user.role not in {"editor", "admin", "system_admin"}:
        api_metrics.TTS_PREVIEW_REQUESTS_TOTAL.labels(outcome="forbidden").inc()
        raise HTTPException(status_code=403, detail="Insufficient role for audio preview")


def preview_rate_limit_key(user: UserContext, request: Request) -> str:
    # Include tenant+user+IP to bound abuse while keeping per-user fairness.
    # NOTE: behind a reverse proxy this may be the proxy IP, not end-user IP.
    client_ip = request.client.host if request.client else "unknown"
    return f"tts_preview:{user.tenant_id}:{user.sub}:{client_ip}"


async def synthesize_preview_wav(
    db: AsyncSession,
    *,
    tenant_id: str,
    text: str,
    tts_voice: str,
    provider_state_pool: object | None = None,
) -> bytes:
    try:
        tts_provider = await resolve_tenant_preview_tts_provider(
            db,
            tenant_id=tenant_id,
            tts_voice=tts_voice,
        )
    except Exception as exc:
        raise preview_provider_http_error(exc) from exc

    catalog_provider_id = str(getattr(tts_provider, "catalog_provider_id", "") or "").strip()
    if catalog_provider_id:
        await assert_provider_quota_available(
            db,
            tenant_id=tenant_id,
            provider_id=catalog_provider_id,
            runtime_scope="api",
            capability="tts",
            source="preview_tts",
            estimated_usage={
                "characters": len(text),
                "requests": 1,
            },
        )

    breaker = get_preview_tts_circuit_breaker(tts_provider.provider_id)

    async def _request() -> bytes:
        return await tts_provider.synthesize_wav(
            text=text,
            timeout_s=settings.tts_preview_request_timeout_s,
            response_format="wav",
        )

    def _record_transition_and_publish(transition: CircuitTransition) -> None:
        _record_preview_tts_transition(
            provider=tts_provider.provider_id,
            transition=transition,
        )
        state = _known_provider_state(transition.to_state.value)
        if state is not None:
            _schedule_preview_circuit_snapshot_write(
                provider=tts_provider.provider_id,
                redis_pool=provider_state_pool,
                state=state,
            )

    def _record_reject_and_publish(state_obj: object) -> None:
        _record_preview_tts_reject(
            provider=tts_provider.provider_id,
            state=state_obj,
        )
        state = _known_provider_state(str(getattr(state_obj, "value", state_obj)))
        if state is not None:
            _schedule_preview_circuit_snapshot_write(
                provider=tts_provider.provider_id,
                redis_pool=provider_state_pool,
                state=state,
            )

    try:
        wav = await breaker.call(
            _request,
            on_transition=_record_transition_and_publish,
            on_reject=_record_reject_and_publish,
        )
    except CircuitOpenError as exc:
        api_metrics.PROVIDER_API_CALLS_TOTAL.labels(
            provider=tts_provider.provider_id,
            service="tts",
            model=tts_provider.model_label,
            outcome="circuit_open",
        ).inc()
        raise HTTPException(
            status_code=503,
            detail="TTS preview temporarily unavailable (provider circuit open)",
        ) from exc
    except Exception:
        api_metrics.PROVIDER_API_CALLS_TOTAL.labels(
            provider=tts_provider.provider_id,
            service="tts",
            model=tts_provider.model_label,
            outcome="error",
        ).inc()
        raise

    api_metrics.PROVIDER_API_CALLS_TOTAL.labels(
        provider=tts_provider.provider_id,
        service="tts",
        model=tts_provider.model_label,
        outcome="success",
    ).inc()
    return wav
