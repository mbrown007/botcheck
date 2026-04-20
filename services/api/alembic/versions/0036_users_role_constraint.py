"""Normalize legacy user roles and enforce the Phase 20 role set.

Revision ID: 0036_users_role_constraint
Revises: 0035_schedule_retry_fields
Create Date: 2026-03-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_users_role_constraint"
down_revision: Union[str, None] = "0035_schedule_retry_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID_ROLES = ("viewer", "operator", "editor", "admin", "system_admin")


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=bind)

    bind.execute(
        users.update()
        .where(~users.c.role.in_(_VALID_ROLES))
        .values(role="viewer")
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role",
            "role IN ('viewer', 'operator', 'editor', 'admin', 'system_admin')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
