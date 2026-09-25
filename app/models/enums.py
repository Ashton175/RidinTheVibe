from enum import Enum


class UserRole(str, Enum):
    UPPER_MANAGEMENT = "upper_management"
    SITE_MANAGEMENT = "site_management"
    TECHNICIAN = "technician"


class RiskTier(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class ScheduleEventType(str, Enum):
    INSPECTION = "inspection"
    MAINTENANCE = "maintenance"


class ScheduleEventStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
