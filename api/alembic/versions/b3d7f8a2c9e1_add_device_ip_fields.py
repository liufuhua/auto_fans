"""add device ip fields

Revision ID: b3d7f8a2c9e1
Revises: a8f4e6d1b9c2
Create Date: 2026-05-09 18:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d7f8a2c9e1"
down_revision: str | Sequence[str] | None = "a8f4e6d1b9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("public_ip", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("ip_province", sa.String(length=32), nullable=True))
    op.add_column("devices", sa.Column("ip_city", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("ip_region", sa.String(length=128), nullable=True))
    op.add_column("devices", sa.Column("ip_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "ip_checked_at")
    op.drop_column("devices", "ip_region")
    op.drop_column("devices", "ip_city")
    op.drop_column("devices", "ip_province")
    op.drop_column("devices", "public_ip")
