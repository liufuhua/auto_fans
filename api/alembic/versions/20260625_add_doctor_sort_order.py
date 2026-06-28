"""add doctor sort order

Revision ID: 20260625_add_doctor_sort_order
Revises: 20260618_add_device_model
Create Date: 2026-06-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260625_add_doctor_sort_order"
down_revision = "20260618_add_device_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE doctors d
        JOIN (
            SELECT ranked_ids.id, (@row_number := @row_number + 1) AS row_num
            FROM (
                SELECT id
                FROM doctors
                WHERE status <> 'deleted'
                ORDER BY id ASC
            ) ranked_ids
            CROSS JOIN (SELECT @row_number := 0) vars
        ) ranked ON ranked.id = d.id
        SET d.sort_order = ranked.row_num
        """
    )


def downgrade() -> None:
    op.drop_column("doctors", "sort_order")
