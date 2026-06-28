from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CommentRecheckRecord(TimestampMixin, Base):
    __tablename__ = "comment_recheck_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    automation_result_id: Mapped[int] = mapped_column(
        ForeignKey("automation_results.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
