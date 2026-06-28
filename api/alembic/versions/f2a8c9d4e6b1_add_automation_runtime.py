"""add automation runtime

Revision ID: f2a8c9d4e6b1
Revises: d4c9b7a6e5f1
Create Date: 2026-05-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a8c9d4e6b1"
down_revision: str | None = "d4c9b7a6e5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_runtime",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("business_status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_automation_runtime_business_status"),
        "automation_runtime",
        ["business_status"],
        unique=False,
    )
    op.execute(
        "INSERT INTO automation_runtime "
        "(id, business_status, remark, created_at, updated_at) "
        "VALUES (1, 'stopped', '', NOW(), NOW())"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_automation_runtime_business_status"), table_name="automation_runtime")
    op.drop_table("automation_runtime")
