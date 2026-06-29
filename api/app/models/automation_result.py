from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AutomationResult(TimestampMixin, Base):
    __tablename__ = "automation_results"
    __table_args__ = (
        Index("ix_automation_results_task_status", "task_id", "status"),
        Index("ix_automation_results_doctor_keyword", "doctor_id", "keyword_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("daily_tasks.id"), index=True, nullable=False)
    task_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_task_items.id"), nullable=True
    )
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctor_keywords.id"), index=True, nullable=True
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    comment_bank_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("comment_bank_items.id"),
        nullable=True,
    )
    publish_account: Mapped[str] = mapped_column(String(100), nullable=False)
    comment_content: Mapped[str] = mapped_column(Text, nullable=False)
    video_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    log_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
