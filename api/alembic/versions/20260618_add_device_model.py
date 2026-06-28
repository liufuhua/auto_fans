"""add device model

Revision ID: 20260618_add_device_model
Revises: 20260610_add_doctor_real_name
Create Date: 2026-06-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260618_add_device_model"
down_revision = "20260610_add_doctor_real_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "device_model",
            sa.String(length=32),
            nullable=False,
            server_default="huawei_nova_se6",
        ),
    )
    op.execute(
        "UPDATE devices SET device_model = 'vivo_y52' "
        "WHERE udid = 'R8594XIBXWXWKRVO'"
    )


def downgrade() -> None:
    op.drop_column("devices", "device_model")
