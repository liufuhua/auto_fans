from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RegionRelation(TimestampMixin, Base):
    __tablename__ = "region_relations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    neighbors: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
