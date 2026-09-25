from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ScheduleEventStatus, ScheduleEventType


class MaintenanceScheduleEvent(TimestampMixin, Base):
    """Planned inspection or maintenance event assigned to an asset and site."""

    __tablename__ = "maintenance_schedule_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[ScheduleEventType] = mapped_column(
        Enum(
            ScheduleEventType,
            name="schedule_event_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_duration: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Estimated duration in minutes"
    )
    resources_needed: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ScheduleEventStatus] = mapped_column(
        Enum(
            ScheduleEventStatus,
            name="schedule_event_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ScheduleEventStatus.SCHEDULED,
        server_default=ScheduleEventStatus.SCHEDULED.value,
    )
    source_risk_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[int] = mapped_column(
        "created_by", ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    asset: Mapped[Asset] = relationship(back_populates="schedule_events")
    site: Mapped[Site] = relationship(back_populates="schedule_events", foreign_keys=[site_id])
    source_risk_assessment: Mapped[RiskAssessment | None] = relationship(
        back_populates="schedule_events"
    )
    creator: Mapped[User] = relationship(back_populates="created_schedule_events")


from app.models.asset import Asset  # noqa: E402
from app.models.risk import RiskAssessment  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.user import User  # noqa: E402
