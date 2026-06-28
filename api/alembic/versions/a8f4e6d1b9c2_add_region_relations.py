"""add region relations

Revision ID: a8f4e6d1b9c2
Revises: 7a1f0e9d2c4b
Create Date: 2026-05-09 18:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8f4e6d1b9c2"
down_revision: str | Sequence[str] | None = "7a1f0e9d2c4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "region_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("neighbors", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region"),
    )
    op.create_index(op.f("ix_region_relations_region"), "region_relations", ["region"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_region_relations_region"), table_name="region_relations")
    op.drop_table("region_relations")
