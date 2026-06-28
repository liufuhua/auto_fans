from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Doctor(TimestampMixin, Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    real_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    name_pinyin: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    real_name_pinyin: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)

    keywords: Mapped[list["DoctorKeyword"]] = relationship(
        back_populates="doctor",
        cascade="all, delete-orphan",
    )


class DoctorKeyword(TimestampMixin, Base):
    __tablename__ = "doctor_keywords"
    __table_args__ = (UniqueConstraint("doctor_id", "keyword", name="uq_doctor_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)

    doctor: Mapped[Doctor] = relationship(back_populates="keywords")
