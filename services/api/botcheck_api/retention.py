"""Retention policy planning + artifact deletion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aioboto3

from .config import Settings


@dataclass(frozen=True)
class RetentionPlan:
    purge_transcript: bool = False
    delete_artifact: bool = False
    reason: str = ""

    @property
    def has_action(self) -> bool:
        return self.purge_transcript or self.delete_artifact


def _profile_cutoff(profile: str, now: datetime) -> datetime | None:
    normalized = (profile or "standard").strip().lower()
    if normalized == "ephemeral":
        return now - timedelta(hours=24)
    if normalized == "standard":
        return now - timedelta(days=90)
    if normalized == "compliance":
        return now - timedelta(days=365 * 7)
    if normalized == "no_audio":
        return now
    return now - timedelta(days=90)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def build_retention_plan(
    *,
    retention_profile: str,
    created_at: datetime,
    has_artifact: bool,
    has_transcript_data: bool,
    now: datetime,
) -> RetentionPlan:
    profile = (retention_profile or "standard").strip().lower()
    normalized_now = _as_utc_naive(now)
    normalized_created_at = _as_utc_naive(created_at)
    cutoff = _profile_cutoff(profile, normalized_now)
    if cutoff is None or normalized_created_at > cutoff:
        return RetentionPlan()

    if profile == "no_audio":
        # Keep transcript metadata, but never keep artifacts for no-audio tenants.
        return RetentionPlan(
            purge_transcript=False,
            delete_artifact=has_artifact,
            reason="no_audio_artifact_policy",
        )

    return RetentionPlan(
        purge_transcript=has_transcript_data,
        delete_artifact=has_artifact,
        reason=f"{profile}_retention_window_elapsed",
    )


async def delete_report_artifact(settings: Settings, key: str) -> None:
    """Best-effort delete for report artifact key from S3/MinIO."""
    if not key:
        return
    if not settings.s3_access_key or not settings.s3_secret_key:
        raise RuntimeError("S3 credentials are not configured")

    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
        await s3.delete_object(Bucket=settings.s3_bucket_prefix, Key=key)


async def upload_artifact_bytes(
    settings: Settings,
    *,
    key: str,
    body: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    """Upload arbitrary artifact bytes into the configured S3 bucket."""
    if not key:
        raise ValueError("key must not be empty")
    if not settings.s3_access_key or not settings.s3_secret_key:
        raise RuntimeError("S3 credentials are not configured")

    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_prefix,
            Key=key,
            Body=body,
            ContentType=content_type,
        )


async def download_artifact_bytes(settings: Settings, *, key: str) -> tuple[bytes, str]:
    """Download artifact bytes and content type from S3."""
    if not key:
        raise ValueError("key must not be empty")
    if not settings.s3_access_key or not settings.s3_secret_key:
        raise RuntimeError("S3 credentials are not configured")

    session = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    async with session.client("s3", endpoint_url=settings.s3_endpoint_url) as s3:
        response = await s3.get_object(Bucket=settings.s3_bucket_prefix, Key=key)
        body = await response["Body"].read()
        content_type = str(response.get("ContentType") or "application/octet-stream")
        return body, content_type
