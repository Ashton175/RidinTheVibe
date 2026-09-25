from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Organization(TimestampMixin, Base):
    """Top-level customer scope that owns sites and organization-wide users."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    sites: Mapped[list[Site]] = relationship(back_populates="organization")
    users: Mapped[list[User]] = relationship(
        back_populates="organization", foreign_keys="User.organization_id"
    )


from app.models.site import Site  # noqa: E402
from app.models.user import User  # noqa: E402
