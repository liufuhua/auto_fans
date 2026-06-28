"""shift automation result times to beijing

Revision ID: 5c8d2e1f4a6b
Revises: 4b7c1d2e9f03
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c8d2e1f4a6b"
down_revision: str | Sequence[str] | None = "4b7c1d2e9f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE automation_results "
            "SET started_at = DATE_ADD(started_at, INTERVAL 8 HOUR), "
            "finished_at = CASE "
            "WHEN finished_at IS NULL THEN NULL "
            "ELSE DATE_ADD(finished_at, INTERVAL 8 HOUR) "
            "END"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE automation_results "
            "SET started_at = DATE_SUB(started_at, INTERVAL 8 HOUR), "
            "finished_at = CASE "
            "WHEN finished_at IS NULL THEN NULL "
            "ELSE DATE_SUB(finished_at, INTERVAL 8 HOUR) "
            "END"
        )
    )
