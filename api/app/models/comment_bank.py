from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CommentBankItem(TimestampMixin, Base):
    __tablename__ = "comment_bank_items"
    __table_args__ = (
        Index("ix_comment_bank_doctor_keyword_status", "doctor_id", "keyword_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_keywords.id"), index=True, nullable=False
    )
    search_word: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unused", index=True, nullable=False)
    used_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    used_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    used_task_id: Mapped[int | None] = mapped_column(ForeignKey("daily_tasks.id"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
