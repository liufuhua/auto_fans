"""add doctor pinyin fields

Revision ID: 20260625_doctor_pinyin
Revises: 20260625_task_item_order
Create Date: 2026-06-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa

from app.core.pinyin import pinyin_initials


revision = "20260625_doctor_pinyin"
down_revision = "20260625_task_item_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doctors",
        sa.Column("name_pinyin", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "doctors",
        sa.Column(
            "real_name_pinyin", sa.String(length=128), nullable=False, server_default=""
        ),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, name, real_name FROM doctors")).mappings()
    for row in rows:
        name = row["name"] or ""
        real_name = row["real_name"] or name
        connection.execute(
            sa.text(
                """
                UPDATE doctors
                SET name_pinyin = :name_pinyin,
                    real_name_pinyin = :real_name_pinyin
                WHERE id = :doctor_id
                """
            ),
            {
                "doctor_id": row["id"],
                "name_pinyin": pinyin_initials(name),
                "real_name_pinyin": pinyin_initials(real_name),
            },
        )


def downgrade() -> None:
    op.drop_column("doctors", "real_name_pinyin")
    op.drop_column("doctors", "name_pinyin")
