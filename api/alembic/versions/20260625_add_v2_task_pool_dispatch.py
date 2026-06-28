"""add v2 task pool dispatch

Revision ID: 20260625_v2_task_pool
Revises: 20260625_doctor_pinyin
Create Date: 2026-06-25 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260625_v2_task_pool"
down_revision: str | Sequence[str] | None = "20260625_doctor_pinyin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_tasks",
        sa.Column(
            "dispatch_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_dispatched",
        ),
    )
    op.add_column(
        "daily_tasks",
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "daily_tasks",
        sa.Column("dispatch_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("daily_tasks", sa.Column("dispatch_error", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_daily_tasks_dispatch_status"),
        "daily_tasks",
        ["dispatch_status"],
        unique=False,
    )
    op.add_column(
        "daily_task_items",
        sa.Column("dispatched_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "device_task_pool_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("task_item_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("keyword_id", sa.Integer(), nullable=False),
        sa.Column("comment_bank_item_id", sa.Integer(), nullable=False),
        sa.Column("pool_round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pool_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["comment_bank_item_id"], ["comment_bank_items.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.ForeignKeyConstraint(["keyword_id"], ["doctor_keywords.id"]),
        sa.ForeignKeyConstraint(["result_id"], ["automation_results.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["daily_tasks.id"]),
        sa.ForeignKeyConstraint(["task_item_id"], ["daily_task_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_bank_item_id", name="uq_device_task_pool_comment"),
    )
    op.create_index(
        "ix_device_task_pool_device_status",
        "device_task_pool_items",
        ["device_id", "status", "pool_round", "pool_order"],
        unique=False,
    )
    op.create_index(
        "ix_device_task_pool_task_status",
        "device_task_pool_items",
        ["task_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_device_task_pool_task_item",
        "device_task_pool_items",
        ["task_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_device_task_pool_device_task",
        "device_task_pool_items",
        ["device_id", "task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_device_task_pool_device_task", table_name="device_task_pool_items")
    op.drop_index("ix_device_task_pool_task_item", table_name="device_task_pool_items")
    op.drop_index("ix_device_task_pool_task_status", table_name="device_task_pool_items")
    op.drop_index("ix_device_task_pool_device_status", table_name="device_task_pool_items")
    op.drop_table("device_task_pool_items")
    op.drop_column("daily_task_items", "dispatched_count")
    op.drop_index(op.f("ix_daily_tasks_dispatch_status"), table_name="daily_tasks")
    op.drop_column("daily_tasks", "dispatch_error")
    op.drop_column("daily_tasks", "dispatch_finished_at")
    op.drop_column("daily_tasks", "dispatch_started_at")
    op.drop_column("daily_tasks", "dispatch_status")
