"""add automation timing settings

Revision ID: 9c2d1e4f6a7b
Revises: f2a8c9d4e6b1
Create Date: 2026-05-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c2d1e4f6a7b"
down_revision: str | Sequence[str] | None = "f2a8c9d4e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_ROWS = (
    ("before_input", "点击首页搜索入口后", 3, 15),
    ("after_input", "输入搜索词后", 2, 5),
    ("after_search", "点击搜索按钮后", 2, 3),
    ("watch_video", "视频观看时长", 15, 300),
    ("after_like", "点赞后", 3, 20),
    ("after_favorite", "收藏后", 3, 20),
    ("comment_pre_input_click", "点击评论输入框后", 2, 5),
    ("comment_focus", "重连后聚焦评论输入框", 2, 5),
    ("after_comment_input", "评论输入后", 5, 5),
    ("before_send_comment", "发送评论前", 0, 0),
)


def upgrade() -> None:
    op.create_table(
        "automation_timing_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("min_seconds", sa.Float(), nullable=False),
        sa.Column("max_seconds", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_automation_timing_settings_key"),
        "automation_timing_settings",
        ["key"],
        unique=True,
    )
    for key, label, min_seconds, max_seconds in DEFAULT_ROWS:
        op.execute(
            sa.text(
                "INSERT INTO automation_timing_settings "
                "(`key`, label, min_seconds, max_seconds, created_at, updated_at) "
                "VALUES (:key, :label, :min_seconds, :max_seconds, NOW(), NOW())"
            ).bindparams(
                key=key,
                label=label,
                min_seconds=min_seconds,
                max_seconds=max_seconds,
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_automation_timing_settings_key"), table_name="automation_timing_settings")
    op.drop_table("automation_timing_settings")
