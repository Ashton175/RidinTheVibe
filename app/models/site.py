from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Site(TimestampMixin, Base):
    """Operational location belonging to one organization."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_sites_id_organization"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="sites")
    users: Mapped[list[User]] = relationship(back_populates="site", foreign_keys="User.site_id")
    assets: Mapped[list[Asset]] = relationship(back_populates="site")
    schedule_events: Mapped[list[MaintenanceScheduleEvent]] = relationship(back_populates="site")


from app.models.asset import Asset  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.schedule import MaintenanceScheduleEvent  # noqa: E402
from app.models.user import User  # noqa: E402
