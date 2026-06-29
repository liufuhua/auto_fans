"""Allow comment bank imports without keywords.

Revision ID: 20260629_optional_keywords
Revises: 20260625_v2_task_pool
Create Date: 2026-06-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260629_optional_keywords"
down_revision: str | Sequence[str] | None = "20260625_v2_task_pool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "comment_bank_items",
        "keyword_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "comment_bank_items",
        "search_word",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        "automation_results",
        "keyword_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE comment_bank_items SET search_word = '' WHERE search_word IS NULL")
    op.alter_column(
        "automation_results",
        "keyword_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "comment_bank_items",
        "search_word",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "comment_bank_items",
        "keyword_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
