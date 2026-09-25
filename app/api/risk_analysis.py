from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import ensure_site_access, get_authorized_site, require_role
from app.db.session import get_db
from app.models import Asset, Inspection, RiskAssessment, Site, User
from app.models.enums import RiskTier, UserRole
from app.schemas.risk import RiskAnalysisResponse
from app.services.ai_explainer import generate_explanation
from app.services.risk_engine import analyze_assets

router = APIRouter(tags=["risk analysis"])
MANAGEMENT_ROLES = (UserRole.UPPER_MANAGEMENT, UserRole.SITE_MANAGEMENT)


def _analyze_and_commit(db: Session, assets: list[Asset]) -> RiskAnalysisResponse:
    """Run the scoring service and commit one assessment for every selected asset."""
    try:
        response = analyze_assets(db, assets)
        db.commit()
        explanations = _generate_explanations(response)
        _persist_explanations(db, explanations)
        return response
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Risk analysis could not be saved. Check the database and try again.",
        ) from None


@dataclass(frozen=True)
class _ExplanationAsset:
    id: int
    asset_tag: str
    name: str
    type: str
    current_condition: str | None


@dataclass(frozen=True)
class _ExplanationInspection:
    inspection_date: date
    vibration_reading: float | None
    visual_condition: str | None
    notes: str | None


@dataclass(frozen=True)
class _ExplanationAssessment:
    risk_score: float
    risk_tier: RiskTier
    probability_of_failure: float
    is_new_issue: bool
    is_recurring_issue: bool


def _generate_explanations(response: RiskAnalysisResponse) -> dict[int, str]:
    """Call the independent explainer once per asset without holding a DB transaction."""
    items = response.high + response.moderate + response.low
    if not items:
        return {}

    explanations: dict[int, str] = {}
    for item in items:
        asset = _ExplanationAsset(
            id=item.asset.id,
            asset_tag=item.asset.asset_tag,
            name=item.asset.name,
            type=item.asset.type,
            current_condition=item.asset.current_condition,
        )
        inspection = (
            _ExplanationInspection(
                inspection_date=item.triggering_inspection.inspection_date,
                vibration_reading=item.triggering_inspection.vibration_reading,
                visual_condition=item.triggering_inspection.visual_condition,
                notes=item.triggering_inspection.notes,
            )
            if item.triggering_inspection
            else None
        )
        assessment = _ExplanationAssessment(
            risk_score=item.risk_score,
            risk_tier=item.risk_tier,
            probability_of_failure=item.probability_of_failure,
            is_new_issue=item.is_new_issue,
            is_recurring_issue=item.is_recurring_issue,
        )
        explanation = generate_explanation(asset, inspection, assessment)
        item.explanation = explanation
        explanations[item.assessment_id] = explanation
    return explanations


def _persist_explanations(
    db: Session, explanations: dict[int, str]
) -> None:
    """Write generated/fallback explanations back to their saved assessments."""
    if not explanations:
        return
    records = db.scalars(
        select(RiskAssessment).where(RiskAssessment.id.in_(explanations))
    ).all()
    for record in records:
        record.ai_explanation = explanations[record.id]
    db.commit()


@router.post("/sites/{site_id}/analyze", response_model=RiskAnalysisResponse)
def analyze_site(
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
) -> RiskAnalysisResponse:
    """Analyze every asset at a site accessible to the current manager."""
    assets = list(
        db.scalars(select(Asset).where(Asset.site_id == site.id).order_by(Asset.asset_tag)).all()
    )
    return _analyze_and_commit(db, assets)


@router.post("/assets/{asset_id}/analyze", response_model=RiskAnalysisResponse)
def analyze_single_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> RiskAnalysisResponse:
    """Analyze one asset after checking its site against the caller's scope."""
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset was not found.")
    ensure_site_access(asset.site_id, db, user)
    return _analyze_and_commit(db, [asset])


__all__ = ["router"]
