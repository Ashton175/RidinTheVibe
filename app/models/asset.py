from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Asset(TimestampMixin, Base):
    """Maintainable equipment registered at a site."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("site_id", "asset_tag", name="uq_assets_site_asset_tag"),
        Index("ix_assets_asset_tag", "asset_tag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_tag: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)

    site: Mapped[Site] = relationship(back_populates="assets")
    inspections: Mapped[list[Inspection]] = relationship(back_populates="asset")
    maintenance_records: Mapped[list[MaintenanceRecord]] = relationship(back_populates="asset")
    risk_assessments: Mapped[list[RiskAssessment]] = relationship(back_populates="asset")
    schedule_events: Mapped[list[MaintenanceScheduleEvent]] = relationship(back_populates="asset")


from app.models.inspection import Inspection  # noqa: E402
from app.models.maintenance import MaintenanceRecord  # noqa: E402
from app.models.risk import RiskAssessment  # noqa: E402
from app.models.schedule import MaintenanceScheduleEvent  # noqa: E402
from app.models.site import Site  # noqa: E402
