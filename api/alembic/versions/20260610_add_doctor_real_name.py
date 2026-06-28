"""add doctor real name

Revision ID: 20260610_add_doctor_real_name
Revises: 6d9e3f2a7b1c
Create Date: 2026-06-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260610_add_doctor_real_name"
down_revision = "6d9e3f2a7b1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column("real_name", sa.String(length=64), nullable=False, server_default=""),
    )
    op.execute("UPDATE doctors SET real_name = name WHERE real_name = ''")


def downgrade() -> None:
    op.drop_column("doctors", "real_name")
