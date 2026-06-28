"""add daily task item sort order

Revision ID: 20260625_task_item_order
Revises: 20260625_add_doctor_sort_order
Create Date: 2026-06-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260625_task_item_order"
down_revision = "20260625_add_doctor_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_task_items",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE daily_task_items item
        JOIN (
            SELECT current_item.id, COUNT(previous_item.id) AS row_num
            FROM daily_task_items current_item
            JOIN daily_task_items previous_item
                ON previous_item.task_id = current_item.task_id
                AND previous_item.id <= current_item.id
            GROUP BY current_item.id
        ) ranked ON ranked.id = item.id
        SET item.sort_order = ranked.row_num
        """
    )


def downgrade() -> None:
    op.drop_column("daily_task_items", "sort_order")
