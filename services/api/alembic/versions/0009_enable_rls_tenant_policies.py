"""Enable tenant row-level-security policies on tenant-scoped tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_expr() -> str:
    return "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Assumption: the application DB user is NOT a PostgreSQL superuser.
    # FORCE ROW LEVEL SECURITY bypasses RLS only for superusers; the app user
    # must be a regular role so policies are enforced at runtime.
    # Alembic runs as the same app user, so migrations execute unrestricted
    # (no app.tenant_id is set during schema changes — this is correct).

    tenant_expr = _tenant_expr()
    for table, policy in (
        ("scenarios", "scenarios_tenant_isolation"),
        ("runs", "runs_tenant_isolation"),
        ("audit_log", "audit_log_tenant_isolation"),
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"USING ({tenant_expr}) "
            f"WITH CHECK ({tenant_expr})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, policy in (
        ("audit_log", "audit_log_tenant_isolation"),
        ("runs", "runs_tenant_isolation"),
        ("scenarios", "scenarios_tenant_isolation"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
