from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DeviceTaskPoolItem(TimestampMixin, Base):
    __tablename__ = "device_task_pool_items"
    __table_args__ = (
        UniqueConstraint("comment_bank_item_id", name="uq_device_task_pool_comment"),
        Index(
            "ix_device_task_pool_device_status",
            "device_id",
            "status",
            "pool_round",
            "pool_order",
        ),
        Index("ix_device_task_pool_task_status", "task_id", "status"),
        Index("ix_device_task_pool_task_item", "task_item_id"),
        Index("ix_device_task_pool_device_task", "device_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("daily_tasks.id"), index=True, nullable=False)
    task_item_id: Mapped[int] = mapped_column(
        ForeignKey("daily_task_items.id"), index=True, nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_keywords.id"), index=True, nullable=False
    )
    comment_bank_item_id: Mapped[int] = mapped_column(
        ForeignKey("comment_bank_items.id"), index=True, nullable=False
    )
    pool_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pool_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_results.id"), nullable=True
    )
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("DailyTask")
    task_item = relationship("DailyTaskItem")
    device = relationship("Device")
    doctor = relationship("Doctor")
    keyword = relationship("DoctorKeyword")
    comment = relationship("CommentBankItem")
