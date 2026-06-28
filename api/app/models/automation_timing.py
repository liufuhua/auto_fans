from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AutomationTimingSetting(TimestampMixin, Base):
    __tablename__ = "automation_timing_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    min_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    max_seconds: Mapped[float] = mapped_column(Float, nullable=False)
