"""add device and doctor province

Revision ID: c6e5a1d4f2b8
Revises: b3d7f8a2c9e1
Create Date: 2026-05-09 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6e5a1d4f2b8"
down_revision: str | Sequence[str] | None = "b3d7f8a2c9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("province", sa.String(length=32), server_default="", nullable=False),
    )
    op.add_column(
        "doctors",
        sa.Column("province", sa.String(length=32), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("doctors", "province")
    op.drop_column("devices", "province")
