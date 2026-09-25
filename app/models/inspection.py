from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Inspection(TimestampMixin, Base):
    """Recorded condition check and measurements for an asset."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inspection_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    inspector_name: Mapped[str] = mapped_column(String(200), nullable=False)
    vibration_reading: Mapped[float | None] = mapped_column(Float, nullable=True)
    visual_condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    asset: Mapped[Asset] = relationship(back_populates="inspections")
    risk_assessments: Mapped[list[RiskAssessment]] = relationship(back_populates="inspection")


from app.models.asset import Asset  # noqa: E402
from app.models.risk import RiskAssessment  # noqa: E402
