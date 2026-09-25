"""Explainable, heuristic asset-risk scoring for the hackathon demo.

Weights, thresholds, condition mappings, and baselines are intentionally named
constants so the team can tune them without rewriting the scoring functions.
The heuristic probability mapping is a placeholder for a calibrated model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Inspection, MaintenanceRecord, RiskAssessment
from app.models.enums import RiskTier
from app.schemas.risk import (
    InspectionTrigger,
    RiskAnalysisItem,
    RiskAnalysisResponse,
    RiskAssetInfo,
)

# Score components are each normalized to 0..100; these weights sum to 1.0.
SCORE_WEIGHTS = {
    "vibration": 0.25,
    "visual_condition": 0.25,
    "maintenance_recency": 0.20,
    "asset_age": 0.12,
    "asset_type_baseline": 0.18,
}

ASSET_TYPE_BASELINE_RISK = {
    "transformer": 65.0,
    "valve": 42.0,
    "gate": 48.0,
}
DEFAULT_ASSET_TYPE_BASELINE_RISK = 40.0

VIBRATION_NORMAL_MAX = 4.5
VIBRATION_CRITICAL = 15.0
MISSING_INDICATOR_SCORE = 20.0

MAINTENANCE_WARNING_DAYS = 365
MAINTENANCE_HIGH_RISK_DAYS = 730
MAINTENANCE_CRITICAL_DAYS = 1095
NO_MAINTENANCE_HISTORY_SCORE = 70.0

AGE_LOW_RISK_YEARS = 5.0
AGE_HIGH_RISK_YEARS = 40.0
UNKNOWN_AGE_SCORE = 25.0

HIGH_RISK_THRESHOLD = 70.0
MODERATE_RISK_THRESHOLD = 30.0
RECURRING_ISSUE_BOOST = 14.0
NEW_ISSUE_BOOST = 10.0
ISSUE_CONDITION_THRESHOLD = 40.0
SIMILAR_NOTE_JACCARD_THRESHOLD = 0.40

VISUAL_CONDITION_SCORES = {
    "healthy": 0.0,
    "excellent": 0.0,
    "good": 0.0,
    "normal": 0.0,
    "satisfactory": 10.0,
    "fair": 35.0,
    "watch": 40.0,
    "aging": 45.0,
    "worn": 55.0,
    "poor": 70.0,
    "degraded": 75.0,
    "bad": 75.0,
    "repair": 80.0,
    "critical": 100.0,
    "failed": 100.0,
    "failing": 100.0,
    "severe": 100.0,
    "dangerous": 100.0,
}
UNKNOWN_VISUAL_CONDITION_SCORE = 30.0

# Map spelling variations to stable issue labels for recurrence detection.
ISSUE_KEYWORD_GROUPS = {
    "leak": ("leak", "leaking", "leakage"),
    "corrosion": ("corrosion", "corroded", "rust", "rusted"),
    "crack": ("crack", "cracked", "fracture"),
    "vibration": ("vibration", "vibrating", "imbalance"),
    "noise": ("noise", "noisy", "rattle", "rattling"),
    "overheat": ("overheat", "overheating", "hot", "temperature"),
    "wear": ("wear", "worn", "erosion"),
    "electrical": ("electrical", "short", "arcing", "insulation"),
    "blockage": ("blockage", "blocked", "clog", "obstruction"),
    "jam": ("jam", "jammed", "stuck", "seized"),
    "damage": ("damage", "damaged", "bent", "broken"),
    "failure": ("failure", "failed", "failing", "fault"),
}


@dataclass(frozen=True)
class IssueFlags:
    """Normalized condition and note clues used to identify recurring issues."""

    condition_bucket: str | None
    keywords: frozenset[str]
    note_tokens: frozenset[str]

    @property
    def has_issue(self) -> bool:
        return self.condition_bucket is not None or bool(self.keywords)


@dataclass(frozen=True)
class RiskCalculation:
    """Internal score result and component breakdown for one asset."""

    score: float
    tier: RiskTier
    probability: float
    recurring: bool
    new_issue: bool
    explanation: str


def clamp_score(value: float) -> float:
    """Clamp a component or total risk score to the documented 0..100 range."""
    return max(0.0, min(100.0, value))


def score_vibration(reading: float | None) -> float:
    """Score vibration above a configurable normal maximum and critical limit."""
    if reading is None:
        return MISSING_INDICATOR_SCORE
    if reading <= VIBRATION_NORMAL_MAX:
        return 0.0
    span = VIBRATION_CRITICAL - VIBRATION_NORMAL_MAX
    return clamp_score((reading - VIBRATION_NORMAL_MAX) / span * 100.0)


def score_visual_condition(condition: str | None) -> float:
    """Translate common visual-condition words into a normalized severity score."""
    if not condition or not condition.strip():
        return MISSING_INDICATOR_SCORE
    normalized = re.sub(r"[^a-z]+", " ", condition.casefold()).strip()
    words = normalized.split()
    for key, score in sorted(VISUAL_CONDITION_SCORES.items(), key=lambda item: -len(item[0])):
        if key in words or any(word.startswith(key) for word in words):
            return score
    return UNKNOWN_VISUAL_CONDITION_SCORE


def score_maintenance_recency(last_maintenance: date | None, as_of: date) -> float:
    """Increase risk as the last maintenance becomes older; unknown history is penalized."""
    if last_maintenance is None:
        return NO_MAINTENANCE_HISTORY_SCORE
    days = max(0, (as_of - last_maintenance).days)
    if days <= MAINTENANCE_WARNING_DAYS:
        return days / MAINTENANCE_WARNING_DAYS * 25.0
    if days <= MAINTENANCE_HIGH_RISK_DAYS:
        fraction = (days - MAINTENANCE_WARNING_DAYS) / (
            MAINTENANCE_HIGH_RISK_DAYS - MAINTENANCE_WARNING_DAYS
        )
        return 25.0 + fraction * 40.0
    if days <= MAINTENANCE_CRITICAL_DAYS:
        fraction = (days - MAINTENANCE_HIGH_RISK_DAYS) / (
            MAINTENANCE_CRITICAL_DAYS - MAINTENANCE_HIGH_RISK_DAYS
        )
        return 65.0 + fraction * 35.0
    return 100.0


def score_asset_age(install_date: date | None, as_of: date) -> float:
    """Score age linearly between the configured low-risk and high-risk ages."""
    if install_date is None:
        return UNKNOWN_AGE_SCORE
    age_days = max(0, (as_of - install_date).days)
    age_years = age_days / 365.25
    if age_years <= AGE_LOW_RISK_YEARS:
        return 0.0
    return clamp_score(
        (age_years - AGE_LOW_RISK_YEARS) / (AGE_HIGH_RISK_YEARS - AGE_LOW_RISK_YEARS) * 100.0
    )


def score_asset_type_baseline(asset_type: str) -> float:
    """Return a tunable baseline for known types, or a conservative default."""
    return ASSET_TYPE_BASELINE_RISK.get(asset_type.strip().casefold(), DEFAULT_ASSET_TYPE_BASELINE_RISK)


def risk_tier_for(score: float) -> RiskTier:
    """Map a 0..100 score to its named risk tier threshold."""
    if score >= HIGH_RISK_THRESHOLD:
        return RiskTier.HIGH
    if score >= MODERATE_RISK_THRESHOLD:
        return RiskTier.MODERATE
    return RiskTier.LOW


def probability_from_score(score: float) -> float:
    """Heuristic probability curve; replace this function with a calibrated model later.

    The convex curve keeps low scores near a 1% floor and sharply raises probability
    for high scores: p = 0.01 + 0.98 * (score / 100)^2. It is a demo heuristic,
    not a statistically calibrated probability of failure.
    """
    normalized = clamp_score(score) / 100.0
    return max(0.0, min(1.0, 0.01 + 0.98 * normalized**2))


def _condition_bucket(condition: str | None) -> str | None:
    score = score_visual_condition(condition)
    if score < ISSUE_CONDITION_THRESHOLD:
        return None
    if score >= 90.0:
        return "critical_visual_condition"
    if score >= 65.0:
        return "poor_visual_condition"
    return "elevated_visual_condition"


def _issue_keywords(text: str) -> frozenset[str]:
    words = set(re.findall(r"[a-z]+", text.casefold()))
    found = {
        group
        for group, variants in ISSUE_KEYWORD_GROUPS.items()
        if any(variant in words or any(word.startswith(variant) for word in words) for variant in variants)
    }
    return frozenset(found)


def issue_flags(inspection: Inspection) -> IssueFlags:
    """Extract comparable issue clues from an inspection's condition and notes."""
    condition = inspection.visual_condition or ""
    notes = inspection.notes or ""
    return IssueFlags(
        condition_bucket=_condition_bucket(condition),
        keywords=_issue_keywords(f"{condition} {notes}"),
        note_tokens=frozenset(
            token for token in re.findall(r"[a-z]{3,}", notes.casefold()) if token not in COMMON_NOTE_WORDS
        ),
    )


COMMON_NOTE_WORDS = frozenset(
    {"the", "and", "with", "from", "that", "this", "was", "were", "has", "have", "for", "not", "but", "into", "during", "inspection", "observed", "found", "unit", "asset"}
)


def inspections_describe_same_issue(first: Inspection, second: Inspection) -> bool:
    """Return true when two inspections share a condition flag or similar note clues."""
    first_flags = issue_flags(first)
    second_flags = issue_flags(second)
    if not first_flags.has_issue or not second_flags.has_issue:
        return False
    if first_flags.condition_bucket and first_flags.condition_bucket == second_flags.condition_bucket:
        return True
    if first_flags.keywords.intersection(second_flags.keywords):
        return True
    union = first_flags.note_tokens | second_flags.note_tokens
    if not union:
        return False
    similarity = len(first_flags.note_tokens & second_flags.note_tokens) / len(union)
    return similarity >= SIMILAR_NOTE_JACCARD_THRESHOLD


def identify_issue_status(history: list[Inspection]) -> tuple[bool, bool]:
    """Return (recurring, new) using the newest inspection and last three records."""
    if not history:
        return False, False
    current = history[0]
    current_flags = issue_flags(current)
    if not current_flags.has_issue:
        return False, False

    recent = history[:3]
    similar_recent_count = sum(
        1 for inspection in recent if inspections_describe_same_issue(current, inspection)
    )
    recurring = similar_recent_count >= 2
    previous = history[1] if len(history) > 1 else None
    new_issue = previous is None or not inspections_describe_same_issue(current, previous)
    return recurring, new_issue


def combine_risk_components(
    *,
    vibration: float,
    visual_condition: float,
    maintenance_recency: float,
    asset_age: float,
    asset_type_baseline: float,
    is_recurring_issue: bool,
    is_new_issue: bool,
) -> float:
    """Weight normalized risk components and apply named urgency boosts."""
    weighted = (
        SCORE_WEIGHTS["vibration"] * vibration
        + SCORE_WEIGHTS["visual_condition"] * visual_condition
        + SCORE_WEIGHTS["maintenance_recency"] * maintenance_recency
        + SCORE_WEIGHTS["asset_age"] * asset_age
        + SCORE_WEIGHTS["asset_type_baseline"] * asset_type_baseline
    )
    urgency_boost = 0.0
    if is_recurring_issue:
        urgency_boost += RECURRING_ISSUE_BOOST
    if is_new_issue:
        urgency_boost += NEW_ISSUE_BOOST
    return round(clamp_score(weighted + urgency_boost), 2)


def calculate_asset_risk(
    asset: Asset,
    inspection_history: list[Inspection],
    maintenance_history: list[MaintenanceRecord],
    as_of: date,
) -> RiskCalculation:
    """Calculate all score factors and an explanation for one asset."""
    latest = inspection_history[0] if inspection_history else None
    recent_visual = latest.visual_condition if latest and latest.visual_condition else asset.current_condition
    last_maintenance = maintenance_history[0].maintenance_date if maintenance_history else None
    vibration_score = score_vibration(latest.vibration_reading if latest else None)
    visual_score = score_visual_condition(recent_visual)
    maintenance_score = score_maintenance_recency(last_maintenance, as_of)
    age_score = score_asset_age(asset.install_date, as_of)
    baseline_score = score_asset_type_baseline(asset.type)
    recurring, new_issue = identify_issue_status(inspection_history)
    total = combine_risk_components(
        vibration=vibration_score,
        visual_condition=visual_score,
        maintenance_recency=maintenance_score,
        asset_age=age_score,
        asset_type_baseline=baseline_score,
        is_recurring_issue=recurring,
        is_new_issue=new_issue,
    )
    probability = round(probability_from_score(total), 4)
    tier = risk_tier_for(total)
    explanation = (
        "Heuristic score components (0-100): "
        f"vibration={vibration_score:.1f}, visual_condition={visual_score:.1f}, "
        f"maintenance_recency={maintenance_score:.1f}, asset_age={age_score:.1f}, "
        f"asset_type_baseline={baseline_score:.1f}. "
        f"Urgency boosts: recurring={RECURRING_ISSUE_BOOST if recurring else 0:.1f}, "
        f"new_issue={NEW_ISSUE_BOOST if new_issue else 0:.1f}. "
        "Failure probability uses the documented demo heuristic, not a trained model."
    )
    return RiskCalculation(total, tier, probability, recurring, new_issue, explanation)


def _to_item(
    asset: Asset,
    assessment: RiskAssessment,
    latest: Inspection | None,
    last_maintenance: date | None,
    explanation: str,
) -> RiskAnalysisItem:
    trigger = (
        InspectionTrigger(
            id=latest.id,
            inspection_date=latest.inspection_date,
            inspector_name=latest.inspector_name,
            vibration_reading=latest.vibration_reading,
            visual_condition=latest.visual_condition,
            notes=latest.notes,
        )
        if latest
        else None
    )
    return RiskAnalysisItem(
        assessment_id=assessment.id,
        asset=RiskAssetInfo(
            id=asset.id,
            site_id=asset.site_id,
            asset_tag=asset.asset_tag,
            name=asset.name,
            type=asset.type,
            current_condition=asset.current_condition,
        ),
        risk_score=assessment.risk_score,
        risk_tier=assessment.risk_tier,
        probability_of_failure=assessment.probability_of_failure,
        is_new_issue=assessment.is_new_issue,
        is_recurring_issue=assessment.is_recurring_issue,
        triggering_inspection=trigger,
        last_maintenance_date=last_maintenance,
        explanation=explanation,
    )


def analyze_assets(
    db: Session,
    assets: Iterable[Asset],
    as_of: date | None = None,
) -> RiskAnalysisResponse:
    """Score every supplied asset and add one RiskAssessment per asset to the session.

    The caller owns the transaction and should commit after this function returns.
    """
    analysis_date = as_of or datetime.now(timezone.utc).date()
    grouped: dict[RiskTier, list[RiskAnalysisItem]] = {
        RiskTier.HIGH: [],
        RiskTier.MODERATE: [],
        RiskTier.LOW: [],
    }
    pending_items: list[tuple[Asset, RiskAssessment, Inspection | None, date | None, str]] = []

    for asset in assets:
        inspections = list(
            db.scalars(
                select(Inspection)
                .where(Inspection.asset_id == asset.id)
                .order_by(Inspection.inspection_date.desc(), Inspection.id.desc())
            ).all()
        )
        maintenance = list(
            db.scalars(
                select(MaintenanceRecord)
                .where(MaintenanceRecord.asset_id == asset.id)
                .order_by(MaintenanceRecord.maintenance_date.desc(), MaintenanceRecord.id.desc())
            ).all()
        )
        calculation = calculate_asset_risk(asset, inspections, maintenance, analysis_date)
        latest = inspections[0] if inspections else None
        last_maintenance = maintenance[0].maintenance_date if maintenance else None
        assessment = RiskAssessment(
            asset_id=asset.id,
            inspection_id=latest.id if latest else None,
            risk_score=calculation.score,
            risk_tier=calculation.tier,
            probability_of_failure=calculation.probability,
            is_recurring_issue=calculation.recurring,
            is_new_issue=calculation.new_issue,
            ai_explanation=calculation.explanation,
        )
        db.add(assessment)
        pending_items.append((asset, assessment, latest, last_maintenance, calculation.explanation))

    db.flush()
    for asset, assessment, latest, last_maintenance, explanation in pending_items:
        grouped[assessment.risk_tier].append(
            _to_item(asset, assessment, latest, last_maintenance, explanation)
        )

    for items in grouped.values():
        items.sort(key=lambda item: item.risk_score, reverse=True)
    return RiskAnalysisResponse(
        high=grouped[RiskTier.HIGH],
        moderate=grouped[RiskTier.MODERATE],
        low=grouped[RiskTier.LOW],
    )


__all__ = [
    "ASSET_TYPE_BASELINE_RISK",
    "HIGH_RISK_THRESHOLD",
    "MODERATE_RISK_THRESHOLD",
    "SCORE_WEIGHTS",
    "analyze_assets",
    "calculate_asset_risk",
    "identify_issue_status",
    "probability_from_score",
    "risk_tier_for",
]
