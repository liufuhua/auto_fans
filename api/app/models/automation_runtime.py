from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AutomationRuntime(TimestampMixin, Base):
    __tablename__ = "automation_runtime"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    business_status: Mapped[str] = mapped_column(
        String(20), default="stopped", index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)
