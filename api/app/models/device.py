from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    udid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    device_model: Mapped[str] = mapped_column(
        String(32), default="huawei_nova_se6", nullable=False
    )
    system_port: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    enabled_status: Mapped[str] = mapped_column(
        String(20), default="enabled", index=True, nullable=False
    )
    runtime_status: Mapped[str] = mapped_column(
        String(20), default="offline", index=True, nullable=False
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    province: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    ip_province: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appium_server_url = mapped_column(String(255), nullable=True)
