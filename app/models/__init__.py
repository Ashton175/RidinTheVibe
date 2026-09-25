"""SQLAlchemy domain models, imported here for Alembic metadata discovery."""

from app.models.asset import Asset
from app.models.enums import RiskTier, ScheduleEventStatus, ScheduleEventType, UserRole
from app.models.inspection import Inspection
from app.models.maintenance import MaintenanceRecord
from app.models.organization import Organization
from app.models.risk import RiskAssessment
from app.models.schedule import MaintenanceScheduleEvent
from app.models.site import Site
from app.models.user import User

__all__ = [
    "Asset",
    "Inspection",
    "MaintenanceRecord",
    "MaintenanceScheduleEvent",
    "Organization",
    "RiskAssessment",
    "RiskTier",
    "ScheduleEventStatus",
    "ScheduleEventType",
    "Site",
    "User",
    "UserRole",
]
