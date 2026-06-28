"""remove legacy region relations

Revision ID: 4b7c1d2e9f03
Revises: 3f6a2b8c9d10
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b7c1d2e9f03"
down_revision: str | Sequence[str] | None = "3f6a2b8c9d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("doctors", "province")
    op.drop_index(op.f("ix_region_relations_region"), table_name="region_relations")
    op.drop_table("region_relations")


def downgrade() -> None:
    op.create_table(
        "region_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("neighbors", sa.Text(), nullable=False),
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
    op.create_index(op.f("ix_region_relations_region"), "region_relations", ["region"])
    op.add_column(
        "doctors",
        sa.Column("province", sa.String(length=32), server_default="", nullable=False),
    )
