"""add action date to device actions

Revision ID: d4c9b7a6e5f1
Revises: c6e5a1d4f2b8
Create Date: 2026-05-10 16:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4c9b7a6e5f1"
down_revision: str | Sequence[str] | None = "c6e5a1d4f2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "device_doctor_action_records",
        sa.Column("action_date", sa.Date(), nullable=True),
    )
    op.execute(
        """
        UPDATE device_doctor_action_records AS record
        LEFT JOIN daily_tasks AS task ON task.id = record.task_id
        SET record.action_date = COALESCE(task.task_date, DATE(record.acted_at))
        """
    )
    op.alter_column(
        "device_doctor_action_records",
        "action_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.drop_constraint(
        "uq_device_doctor_keyword_action",
        "device_doctor_action_records",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_device_doctor_keyword_action",
        "device_doctor_action_records",
        ["device_id", "doctor_id", "keyword_id", "action_type", "action_date"],
    )
    op.create_index(
        op.f("ix_device_doctor_action_records_action_date"),
        "device_doctor_action_records",
        ["action_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_device_doctor_action_records_action_date"),
        table_name="device_doctor_action_records",
    )
    op.drop_constraint(
        "uq_device_doctor_keyword_action",
        "device_doctor_action_records",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_device_doctor_keyword_action",
        "device_doctor_action_records",
        ["device_id", "doctor_id", "keyword_id", "action_type"],
    )
    op.drop_column("device_doctor_action_records", "action_date")
