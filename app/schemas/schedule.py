from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import RiskTier, ScheduleEventStatus, ScheduleEventType


class ScheduleEventCreate(BaseModel):
    """Fields required to manually add a calendar event to a site's asset."""

    asset_id: int = Field(gt=0)
    scheduled_date: date
    event_type: ScheduleEventType
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    estimated_duration: int | None = Field(default=None, gt=0)
    resources_needed: str | None = None

    @model_validator(mode="after")
    def title_not_blank(self) -> "ScheduleEventCreate":
        if not self.title.strip():
            raise ValueError("title must not be blank.")
        self.title = self.title.strip()
        return self


class RiskScheduleEventCreate(BaseModel):
    """Fields for turning a risk assessment into a scheduled follow-up."""

    scheduled_date: date
    event_type: ScheduleEventType
    notes: str | None = None
    estimated_duration: int | None = Field(default=None, gt=0)
    resources_needed: str | None = None


class ScheduleEventPatch(BaseModel):
    """Partial event update for rescheduling and editing calendar details."""

    scheduled_date: date | None = None
    event_type: ScheduleEventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None
    estimated_duration: int | None = Field(default=None, gt=0)
    resources_needed: str | None = None
    status: ScheduleEventStatus | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "ScheduleEventPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field in ("scheduled_date", "event_type", "title", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        if self.title is not None:
            if not self.title.strip():
                raise ValueError("title must not be blank.")
            self.title = self.title.strip()
        return self


class ScheduleStatusPatch(BaseModel):
    """Status-only transition request for a calendar event."""

    status: ScheduleEventStatus


class ScheduledAssetInfo(BaseModel):
    """Asset information displayed in an event card or tooltip."""

    id: int
    site_id: int
    asset_tag: str
    name: str
    type: str
    current_condition: str | None


class ScheduleRiskInfo(BaseModel):
    """Risk summary that triggered an event, when the event is risk-linked."""

    id: int
    risk_score: float
    risk_tier: RiskTier
    probability_of_failure: float
    is_new_issue: bool
    is_recurring_issue: bool
    ai_explanation: str | None
    created_at: datetime


class ScheduleEventResponse(BaseModel):
    """Calendar event with nested asset and source-risk context."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    asset_id: int
    scheduled_date: date
    event_type: ScheduleEventType
    title: str
    notes: str | None
    estimated_duration: int | None
    resources_needed: str | None
    status: ScheduleEventStatus
    source_risk_assessment_id: int | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    asset: ScheduledAssetInfo
    source_risk_assessment: ScheduleRiskInfo | None
