from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from ..auth import UserContext, require_admin
from ..auth.security import check_login_rate_limit
from ..config import settings
from ..exceptions import GENERATE_RATE_LIMITED, JOB_NOT_FOUND, JOB_QUEUE_UNAVAILABLE, ApiProblem
from .schemas import GenerateJobStatus, GenerateRequest, GenerateStartResponse

router = APIRouter()
logger = logging.getLogger("botcheck.api.scenarios")


@router.post("/generate", response_model=GenerateStartResponse, status_code=202)
async def start_generate_scenarios(
    body: GenerateRequest,
    request: Request,
    user: UserContext = Depends(require_admin),
):
    tenant_id = user.tenant_id
    allowed, retry_after = check_login_rate_limit(
        key=f"generate:{tenant_id}",
        max_attempts=settings.scenario_generator_rate_limit_per_hour,
        window_s=3600,
    )
    if not allowed:
        raise ApiProblem(
            status=429,
            error_code=GENERATE_RATE_LIMITED,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(int(retry_after or 60))},
        )

    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Job queue unavailable",
        )

    job_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    job_state = GenerateJobStatus(
        job_id=job_id,
        status="pending",
        count_requested=body.count,
        count_succeeded=0,
        scenarios=[],
        errors=[],
        created_at=now,
        completed_at=None,
    )
    redis_key = f"botcheck:generate:{job_id}"
    await arq_pool.set(redis_key, job_state.model_dump_json(), ex=3600)

    await arq_pool.enqueue_job(
        "generate_scenarios",
        payload={
            "job_id": job_id,
            "tenant_id": tenant_id,
            "target_system_prompt": body.target_system_prompt,
            "steering_prompt": body.steering_prompt,
            "user_objective": body.user_objective,
            "count": body.count,
        },
        _queue_name="arq:judge",
    )
    logger.info(
        "generate.enqueued",
        extra={"job_id": job_id, "tenant_id": tenant_id, "count": body.count},
    )
    return GenerateStartResponse(job_id=job_id)


@router.get("/generate/{job_id}", response_model=GenerateJobStatus)
async def get_generate_job(
    job_id: str,
    request: Request,
    _: UserContext = Depends(require_admin),
):
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is None:
        raise ApiProblem(
            status=503,
            error_code=JOB_QUEUE_UNAVAILABLE,
            detail="Job queue unavailable",
        )

    redis_key = f"botcheck:generate:{job_id}"
    raw = await arq_pool.get(redis_key)
    if raw is None:
        raise ApiProblem(
            status=404,
            error_code=JOB_NOT_FOUND,
            detail="Job not found",
        )

    return GenerateJobStatus.model_validate_json(raw)
