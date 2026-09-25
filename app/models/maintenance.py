from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MaintenanceRecord(TimestampMixin, Base):
    """Completed or historical maintenance work performed on an asset."""

    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    maintenance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    performed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    asset: Mapped[Asset] = relationship(back_populates="maintenance_records")


from app.models.asset import Asset  # noqa: E402
