from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import RiskTier

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.inspection import Inspection
    from app.models.schedule import MaintenanceScheduleEvent


class RiskAssessment(TimestampMixin, Base):
    """Calculated risk result for an asset, optionally tied to an inspection."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inspection_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(RiskTier, name="risk_tier", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    probability_of_failure: Mapped[float] = mapped_column(Float, nullable=False)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recurring_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_new_issue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    asset: Mapped[Asset] = relationship(back_populates="risk_assessments")
    inspection: Mapped[Inspection | None] = relationship(back_populates="risk_assessments")
    schedule_events: Mapped[list[MaintenanceScheduleEvent]] = relationship(
        back_populates="source_risk_assessment"
    )
