from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DeviceDoctorActionRecord(TimestampMixin, Base):
    __tablename__ = "device_doctor_action_records"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "doctor_id",
            "keyword_id",
            "action_type",
            "action_date",
            name="uq_device_doctor_keyword_action",
        ),
        Index("ix_device_action_doctor_keyword", "doctor_id", "keyword_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_keywords.id"), index=True, nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(ForeignKey("daily_tasks.id"), nullable=True)
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_results.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    action_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="success", index=True, nullable=False)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
