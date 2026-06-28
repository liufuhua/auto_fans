"""add automation result summary

Revision ID: 7a1f0e9d2c4b
Revises: e0d75b15bec7
Create Date: 2026-05-09 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1f0e9d2c4b"
down_revision: str | Sequence[str] | None = "e0d75b15bec7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("automation_results", sa.Column("result_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("automation_results", "result_summary")
