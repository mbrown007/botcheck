import logging

from botcheck_scenarios import GateResult, RunStatus
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import UserContext, get_current_user, get_service_caller
from ..config import settings
from ..database import get_db
from .store_service import append_run_event, get_run, get_run_for_tenant
from ..exceptions import ApiProblem, RECORDING_NOT_FOUND, RUN_NOT_FOUND
from ..models import RetentionProfile, RunState
from ..retention import (
    download_artifact_bytes as retention_download_artifact_bytes,
    upload_artifact_bytes as retention_upload_artifact_bytes,
)
from .runs import GateResponse, RecordingUploadResponse
from .service_state import build_recording_s3_key, parse_recording_format, parse_run_state

router = APIRouter()

logger = logging.getLogger("botcheck.api.runs")


# Wrappers expose stable patch points inside this split module.
async def upload_artifact_bytes(*args, **kwargs):
    return await retention_upload_artifact_bytes(*args, **kwargs)


async def download_artifact_bytes(*args, **kwargs):
    return await retention_download_artifact_bytes(*args, **kwargs)


@router.put("/{run_id}/recording", response_model=RecordingUploadResponse)
async def upload_run_recording(
    run_id: str,
    request: Request,
    format: str = "wav",
    duration_ms: int | None = None,
    db: AsyncSession = Depends(get_db),
    caller: str = Depends(get_service_caller),
):
    if caller != "harness":
        raise HTTPException(status_code=403, detail="Only harness may upload recordings")

    run = await get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    state = parse_run_state(run.state)
    if state in {RunState.COMPLETE, RunState.FAILED, RunState.ERROR}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot upload recording while run is {state.value}",
        )
    if (run.retention_profile or "").strip().lower() == RetentionProfile.NO_AUDIO.value:
        return RecordingUploadResponse(
            ok=True,
            recording_s3_key=None,
            skipped_reason="retention_profile_no_audio",
        )

    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=422, detail="Recording body is empty")
    if len(payload) > settings.recording_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "Recording upload too large"
                f" ({len(payload)} bytes > {settings.recording_max_upload_bytes})"
            ),
        )

    recording_format = parse_recording_format(format)
    key = build_recording_s3_key(
        run_id=run_id,
        tenant_id=run.tenant_id,
        fmt=recording_format,
    )
    content_type = request.headers.get("content-type") or "audio/wav"
    try:
        await upload_artifact_bytes(
            settings,
            key=key,
            body=payload,
            content_type=content_type,
        )
    except Exception:
        logger.exception("Recording upload failed for run %s", run_id)
        raise HTTPException(status_code=503, detail="Recording upload failed")

    run.recording_s3_key = key
    await append_run_event(
        db,
        run_id,
        "recording_uploaded",
        {
            "source": "harness",
            "recording_s3_key": key,
            "bytes": len(payload),
            "format": recording_format,
            "duration_ms": duration_ms,
        },
    )
    await write_audit_event(
        db,
        tenant_id=run.tenant_id,
        actor_id="harness",
        actor_type="service",
        action="run.recording_uploaded",
        resource_type="run",
        resource_id=run_id,
        detail={
            "recording_s3_key": key,
            "bytes": len(payload),
            "duration_ms": duration_ms,
        },
    )
    await db.commit()
    return RecordingUploadResponse(ok=True, recording_s3_key=key)


@router.get("/{run_id}/recording")
async def download_run_recording(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    run = await get_run_for_tenant(db, run_id, user.tenant_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    if not run.recording_s3_key:
        raise ApiProblem(
            status=404,
            error_code=RECORDING_NOT_FOUND,
            detail="Recording not found",
        )
    try:
        body, content_type = await download_artifact_bytes(
            settings,
            key=run.recording_s3_key,
        )
    except Exception as exc:
        err = getattr(exc, "response", {}).get("Error", {})
        code = str(err.get("Code", "")).strip()
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise ApiProblem(
                status=404,
                error_code=RECORDING_NOT_FOUND,
                detail="Recording not found",
            )
        logger.exception("Recording download failed for run %s", run_id)
        raise HTTPException(status_code=503, detail="Recording unavailable")
    return Response(content=body, media_type=content_type)


@router.get("/{run_id}/gate", response_model=GateResponse)
async def get_gate(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """
    CI/CD gate endpoint.
    Returns 200 with gate_result=passed|blocked once judging is complete.
    Returns 202 while the run is still in progress.
    """
    run = await get_run_for_tenant(db, run_id, user.tenant_id)
    if run is None:
        raise ApiProblem(
            status=404,
            error_code=RUN_NOT_FOUND,
            detail="Run not found",
        )
    if run.state not in ("complete", "failed", "error"):
        raise HTTPException(status_code=202, detail=f"Run state: {run.state}")

    return GateResponse(
        run_id=run_id,
        gate_result=GateResult(run.gate_result or "not_applicable"),
        overall_status=RunStatus(run.overall_status) if run.overall_status else None,
        failed_dimensions=run.failed_dimensions or [],
        summary=run.summary,
    )
