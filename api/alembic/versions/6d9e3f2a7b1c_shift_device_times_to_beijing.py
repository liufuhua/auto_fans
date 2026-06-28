"""shift device times to beijing

Revision ID: 6d9e3f2a7b1c
Revises: 5c8d2e1f4a6b
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6d9e3f2a7b1c"
down_revision: str | Sequence[str] | None = "5c8d2e1f4a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE devices "
            "SET last_heartbeat_at = CASE "
            "WHEN last_heartbeat_at IS NULL THEN NULL "
            "ELSE DATE_ADD(last_heartbeat_at, INTERVAL 8 HOUR) "
            "END, "
            "ip_checked_at = CASE "
            "WHEN ip_checked_at IS NULL THEN NULL "
            "ELSE DATE_ADD(ip_checked_at, INTERVAL 8 HOUR) "
            "END"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE devices "
            "SET last_heartbeat_at = CASE "
            "WHEN last_heartbeat_at IS NULL THEN NULL "
            "ELSE DATE_SUB(last_heartbeat_at, INTERVAL 8 HOUR) "
            "END, "
            "ip_checked_at = CASE "
            "WHEN ip_checked_at IS NULL THEN NULL "
            "ELSE DATE_SUB(ip_checked_at, INTERVAL 8 HOUR) "
            "END"
        )
    )
