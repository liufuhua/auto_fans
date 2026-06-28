"""add doctor provinces

Revision ID: 3f6a2b8c9d10
Revises: 9c2d1e4f6a7b
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f6a2b8c9d10"
down_revision: str | Sequence[str] | None = "9c2d1e4f6a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_provinces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("province", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "province", name="uq_doctor_province"),
    )
    op.create_index(op.f("ix_doctor_provinces_doctor_id"), "doctor_provinces", ["doctor_id"])
    op.create_index(op.f("ix_doctor_provinces_province"), "doctor_provinces", ["province"])

    op.execute(
        sa.text(
            "INSERT IGNORE INTO doctor_provinces (doctor_id, province, created_at, updated_at) "
            "SELECT id, province, NOW(), NOW() FROM doctors "
            "WHERE province IS NOT NULL AND TRIM(province) <> ''"
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_doctor_provinces_province"), table_name="doctor_provinces")
    op.drop_index(op.f("ix_doctor_provinces_doctor_id"), table_name="doctor_provinces")
    op.drop_table("doctor_provinces")
