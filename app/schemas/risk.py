from datetime import date

from pydantic import BaseModel

from app.models.enums import RiskTier


class InspectionTrigger(BaseModel):
    """The inspection that supplied the latest condition measurements."""

    id: int
    inspection_date: date
    inspector_name: str
    vibration_reading: float | None
    visual_condition: str | None
    notes: str | None


class RiskAssetInfo(BaseModel):
    """Asset identity fields used by the risk priority list."""

    id: int
    site_id: int
    asset_tag: str
    name: str
    type: str
    current_condition: str | None


class RiskAnalysisItem(BaseModel):
    """One persisted asset risk result with its explanation and source inspection."""

    assessment_id: int
    asset: RiskAssetInfo
    risk_score: float
    risk_tier: RiskTier
    probability_of_failure: float
    is_new_issue: bool
    is_recurring_issue: bool
    triggering_inspection: InspectionTrigger | None
    last_maintenance_date: date | None
    explanation: str


class RiskAnalysisResponse(BaseModel):
    """Risk priority list grouped into high, moderate, and low tiers."""

    high: list[RiskAnalysisItem]
    moderate: list[RiskAnalysisItem]
    low: list[RiskAnalysisItem]
