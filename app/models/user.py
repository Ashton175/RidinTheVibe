from __future__ import annotations

from sqlalchemy import CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole


class User(TimestampMixin, Base):
    """Organization member with a role and optional site-level scope."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_users_id_organization"),
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            name="fk_users_site_organization",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(role = 'upper_management' AND site_id IS NULL) "
            "OR (role <> 'upper_management' AND site_id IS NOT NULL)",
            name="ck_users_role_site_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[int | None] = mapped_column(nullable=True, index=True)

    organization: Mapped[Organization] = relationship(back_populates="users")
    site: Mapped[Site | None] = relationship(back_populates="users", foreign_keys=[site_id])
    created_schedule_events: Mapped[list[MaintenanceScheduleEvent]] = relationship(
        back_populates="creator"
    )


from app.models.organization import Organization  # noqa: E402
from app.models.schedule import MaintenanceScheduleEvent  # noqa: E402
from app.models.site import Site  # noqa: E402
