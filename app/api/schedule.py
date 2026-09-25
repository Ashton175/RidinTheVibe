from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import ensure_site_access, get_authorized_site, require_role
from app.db.session import get_db
from app.models import (
    Asset,
    MaintenanceScheduleEvent,
    RiskAssessment,
    Site,
    User,
)
from app.models.enums import ScheduleEventStatus, UserRole
from app.schemas.schedule import (
    RiskScheduleEventCreate,
    ScheduleEventCreate,
    ScheduleEventPatch,
    ScheduleEventResponse,
    ScheduleStatusPatch,
)

router = APIRouter(tags=["maintenance schedule"])
MANAGEMENT_ROLES = (UserRole.UPPER_MANAGEMENT, UserRole.SITE_MANAGEMENT)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The schedule change could not be saved. Check the database and try again.",
        ) from None


def _get_authorized_event(event_id: int, db: Session, user: User) -> MaintenanceScheduleEvent:
    event = db.scalar(
        select(MaintenanceScheduleEvent)
        .options(
            selectinload(MaintenanceScheduleEvent.asset),
            selectinload(MaintenanceScheduleEvent.source_risk_assessment),
        )
        .where(MaintenanceScheduleEvent.id == event_id)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Schedule event was not found.")
    ensure_site_access(event.site_id, db, user)
    if event.asset.site_id != event.site_id:
        raise HTTPException(status_code=409, detail="Schedule event asset and site do not match.")
    return event


def _check_asset_for_site(asset_id: int, site_id: int, db: Session) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.site_id != site_id:
        raise HTTPException(status_code=404, detail="Asset was not found at this site.")
    return asset


def _refresh_event(db: Session, event: MaintenanceScheduleEvent) -> ScheduleEventResponse:
    db.refresh(event)
    return ScheduleEventResponse.model_validate(event)


@router.get("/sites/{site_id}/schedule", response_model=list[ScheduleEventResponse])
def list_schedule_events(
    start_date: date | None = None,
    end_date: date | None = None,
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
) -> list[ScheduleEventResponse]:
    """List a site's schedule events, optionally bounded by inclusive dates."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")

    statement = (
        select(MaintenanceScheduleEvent)
        .options(
            selectinload(MaintenanceScheduleEvent.asset),
            selectinload(MaintenanceScheduleEvent.source_risk_assessment),
        )
        .where(
            MaintenanceScheduleEvent.site_id == site.id,
            MaintenanceScheduleEvent.asset_id.in_(
                select(Asset.id).where(Asset.site_id == site.id)
            ),
        )
    )
    if start_date is not None:
        statement = statement.where(MaintenanceScheduleEvent.scheduled_date >= start_date)
    if end_date is not None:
        statement = statement.where(MaintenanceScheduleEvent.scheduled_date <= end_date)
    events = db.scalars(
        statement.order_by(MaintenanceScheduleEvent.scheduled_date, MaintenanceScheduleEvent.id)
    ).all()
    return [ScheduleEventResponse.model_validate(event) for event in events]


@router.post(
    "/sites/{site_id}/schedule",
    response_model=ScheduleEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_event(
    payload: ScheduleEventCreate,
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> ScheduleEventResponse:
    """Create a manual event for an asset at the selected site."""
    _check_asset_for_site(payload.asset_id, site.id, db)
    event = MaintenanceScheduleEvent(
        site_id=site.id,
        asset_id=payload.asset_id,
        scheduled_date=payload.scheduled_date,
        event_type=payload.event_type,
        title=payload.title,
        notes=payload.notes,
        estimated_duration=payload.estimated_duration,
        resources_needed=payload.resources_needed,
        status=ScheduleEventStatus.SCHEDULED,
        created_by=user.id,
    )
    db.add(event)
    _commit(db)
    return _refresh_event(db, event)


@router.post(
    "/risk-assessments/{risk_assessment_id}/schedule",
    response_model=ScheduleEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event_from_risk_assessment(
    risk_assessment_id: int,
    payload: RiskScheduleEventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> ScheduleEventResponse:
    """Schedule follow-up work from a risk result and preserve its source link."""
    risk_assessment = db.scalar(
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.asset))
        .where(RiskAssessment.id == risk_assessment_id)
    )
    if risk_assessment is None:
        raise HTTPException(status_code=404, detail="Risk assessment was not found.")
    asset = risk_assessment.asset
    ensure_site_access(asset.site_id, db, user)
    event = MaintenanceScheduleEvent(
        site_id=asset.site_id,
        asset_id=asset.id,
        scheduled_date=payload.scheduled_date,
        event_type=payload.event_type,
        title=f"{risk_assessment.risk_tier.value.title()} risk follow-up: {asset.name}"[:200],
        notes=payload.notes,
        estimated_duration=payload.estimated_duration,
        resources_needed=payload.resources_needed,
        status=ScheduleEventStatus.SCHEDULED,
        source_risk_assessment_id=risk_assessment.id,
        created_by=user.id,
    )
    db.add(event)
    _commit(db)
    return _refresh_event(db, event)


@router.patch("/schedule/{event_id}", response_model=ScheduleEventResponse)
def update_schedule_event(
    event_id: int,
    payload: ScheduleEventPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> ScheduleEventResponse:
    """Partially edit a schedule event while keeping its site and asset fixed."""
    event = _get_authorized_event(event_id, db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    _commit(db)
    return _refresh_event(db, event)


@router.patch("/schedule/{event_id}/status", response_model=ScheduleEventResponse)
def update_schedule_status(
    event_id: int,
    payload: ScheduleStatusPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> ScheduleEventResponse:
    """Set an event's status to scheduled, completed, or cancelled."""
    event = _get_authorized_event(event_id, db, user)
    event.status = payload.status
    _commit(db)
    return _refresh_event(db, event)


@router.delete("/schedule/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*MANAGEMENT_ROLES)),
) -> Response:
    """Delete an event the caller is permitted to manage."""
    event = _get_authorized_event(event_id, db, user)
    db.delete(event)
    _commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
