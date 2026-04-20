from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from botcheck_api import database
from botcheck_api.models import UserRow


async def test_users_table_rejects_invalid_role(db_setup):
    del db_setup
    factory = database.AsyncSessionLocal
    assert factory is not None

    async with factory() as session:
        session.add(
            UserRow(
                user_id="user_invalid_role",
                tenant_id="default",
                email="invalid-role@example.com",
                role="qa_engineer",
                password_hash="hash",
                is_active=True,
                totp_enabled=False,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
