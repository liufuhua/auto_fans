from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DoctorProvince(TimestampMixin, Base):
    __tablename__ = "doctor_provinces"
    __table_args__ = (
        UniqueConstraint("doctor_id", "province", name="uq_doctor_province"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    province: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
