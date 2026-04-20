from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .models import PlatformSettingsRow


async def ensure_platform_settings_row(db: AsyncSession) -> PlatformSettingsRow:
    existing = await db.get(PlatformSettingsRow, "default")
    if existing is not None:
        return existing
    row = PlatformSettingsRow(
        singleton_id="default",
        feature_flags={},
        quota_defaults={},
    )
    db.add(row)
    await db.flush()
    return row
