from __future__ import annotations

import re
import math
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_authorized_site
from app.db.session import get_db
from app.models import Asset, Inspection, MaintenanceRecord, Site, User
from app.schemas.uploads import UploadError, UploadSummary, UnmatchedUploadRow

router = APIRouter(prefix="/sites/{site_id}/upload", tags=["uploads"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ASSET_COLUMNS = {"asset_tag", "name", "type", "condition"}
INSPECTION_COLUMNS = {
    "asset_tag",
    "inspection_date",
    "vibration_reading",
    "visual_condition",
    "notes",
}
MAINTENANCE_COLUMNS = {"asset_tag", "maintenance_date", "description"}


def _normalize_column(column: Any) -> str:
    name = re.sub(r"[\s-]+", "_", str(column).strip().lower())
    name = re.sub(r"[^a-z0-9_]+", "_", name).strip("_")
    aliases = {
        "asset_type": "type",
        "asset_condition": "condition",
        "current_condition": "condition",
        "vibration_mm_s": "vibration_reading",
        "vibration_reading_mm_s": "vibration_reading",
    }
    return aliases.get(name, name)


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-serializable Python values."""
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _as_text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> date | None:
    if _is_missing(value):
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            if 19000101 <= value <= 21001231 and float(value).is_integer():
                parsed = pd.to_datetime(str(int(value)), format="%Y%m%d", errors="coerce")
                return None if _is_missing(parsed) else parsed.date()
            if 10000 <= value <= 100000:
                parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(value, unit="D")
                return parsed.date()
        parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    except (TypeError, ValueError, OverflowError):
        return None
    if _is_missing(parsed):
        return None
    return parsed.date()


def _read_frame(upload: UploadFile) -> tuple[pd.DataFrame | None, str | None]:
    """Read a CSV/XLSX upload, normalizing its headers before validation."""
    filename = (upload.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        return None, "File must use the .csv or .xlsx extension."

    content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return None, "File exceeds the 20 MB upload limit."
    if not content:
        return None, "The uploaded file is empty."

    try:
        if filename.endswith(".xlsx"):
            frame = pd.read_excel(BytesIO(content), engine="openpyxl")
        else:
            try:
                frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig", keep_default_na=False)
            except UnicodeDecodeError:
                frame = pd.read_csv(BytesIO(content), encoding="cp1252", keep_default_na=False)
    except Exception as exc:
        return None, f"Could not read the uploaded file: {exc}"

    normalized = [_normalize_column(column) for column in frame.columns]
    duplicates = sorted({column for column in normalized if normalized.count(column) > 1})
    if duplicates:
        return None, "Multiple columns normalize to the same name: " + ", ".join(duplicates)
    frame.columns = normalized
    return frame, None


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in row.to_dict().items()}


def _summary_for_read_error(message: str) -> UploadSummary:
    return UploadSummary(errors=[UploadError(message=message)])


def _missing_columns_summary(frame: pd.DataFrame, required: set[str]) -> UploadSummary | None:
    missing = sorted(required.difference(frame.columns))
    if not missing:
        return None
    count = len(frame.index)
    return UploadSummary(
        rows_processed=count,
        rows_skipped=count,
        errors=[UploadError(message="Missing required columns: " + ", ".join(missing))],
    )


def _tag_key(value: Any) -> str | None:
    text = _as_text(value)
    return text.casefold() if text is not None else None


def _add_row_error(summary: UploadSummary, row_number: int, message: str) -> None:
    summary.rows_skipped += 1
    summary.errors.append(UploadError(row=row_number, message=message))


def _merge_json(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge file extras without letting blank cells erase existing values."""
    return {**(existing or {}), **{key: value for key, value in incoming.items() if value is not None}}


def _finish_upload(db: Session, summary: UploadSummary) -> UploadSummary:
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        summary.rows_created = 0
        summary.rows_updated = 0
        summary.rows_skipped = summary.rows_processed
        summary.errors.append(
            UploadError(message=f"Could not save the upload; no rows were committed: {exc}")
        )
        return summary
    return summary


@router.post("/assets", response_model=UploadSummary)
def upload_assets(
    file: UploadFile = File(...),
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
) -> UploadSummary:
    """Create or update assets from a site-scoped CSV or XLSX file."""
    frame, error = _read_frame(file)
    if error or frame is None:
        return _summary_for_read_error(error or "Could not read the uploaded file.")
    invalid = _missing_columns_summary(frame, ASSET_COLUMNS)
    if invalid:
        return invalid

    summary = UploadSummary(rows_processed=len(frame.index))
    assets = db.scalars(select(Asset).where(Asset.site_id == site.id)).all()
    assets_by_tag = {_tag_key(asset.asset_tag): asset for asset in assets}
    explicit = ASSET_COLUMNS | {"install_date"}

    for offset, (_, row) in enumerate(frame.iterrows()):
        row_number = offset + 2
        tag = _as_text(row["asset_tag"])
        name = _as_text(row["name"])
        asset_type = _as_text(row["type"])
        condition = _as_text(row["condition"])
        if not all((tag, name, asset_type, condition)):
            _add_row_error(summary, row_number, "asset_tag, name, type, and condition must not be blank.")
            continue

        key = tag.casefold()
        extra = {column: _json_safe(row[column]) for column in frame.columns if column not in explicit}
        asset = assets_by_tag.get(key)
        install_date = _parse_date(row["install_date"]) if "install_date" in frame.columns else None
        if "install_date" in frame.columns and not _is_missing(row["install_date"]) and install_date is None:
            extra["install_date"] = _json_safe(row["install_date"])
            summary.errors.append(
                UploadError(row=row_number, message="Invalid install_date was preserved in metadata.")
            )

        if asset is None:
            asset = Asset(
                site_id=site.id,
                asset_tag=tag,
                name=name,
                type=asset_type,
                current_condition=condition,
                install_date=install_date,
                asset_metadata=extra,
            )
            db.add(asset)
            assets_by_tag[key] = asset
            summary.rows_created += 1
        else:
            asset.name = name
            asset.type = asset_type
            asset.current_condition = condition
            if install_date is not None:
                asset.install_date = install_date
            asset.asset_metadata = _merge_json(asset.asset_metadata, extra)
            summary.rows_updated += 1

    return _finish_upload(db, summary)


@router.post("/inspections", response_model=UploadSummary)
def upload_inspections(
    file: UploadFile = File(...),
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
) -> UploadSummary:
    """Create or update inspections; unmatched tags are reported and skipped."""
    frame, error = _read_frame(file)
    if error or frame is None:
        return _summary_for_read_error(error or "Could not read the uploaded file.")
    invalid = _missing_columns_summary(frame, INSPECTION_COLUMNS)
    if invalid:
        return invalid

    summary = UploadSummary(rows_processed=len(frame.index))
    assets = db.scalars(select(Asset).where(Asset.site_id == site.id)).all()
    assets_by_tag = {_tag_key(asset.asset_tag): asset for asset in assets}
    explicit = INSPECTION_COLUMNS | {"inspector_name"}
    records_by_key: dict[tuple[int, date], Inspection | None] = {}

    for offset, (_, row) in enumerate(frame.iterrows()):
        row_number = offset + 2
        original = _row_dict(row)
        tag = _as_text(row["asset_tag"])
        asset = assets_by_tag.get(_tag_key(tag)) if tag else None
        if asset is None:
            summary.rows_skipped += 1
            summary.unmatched_rows.append(
                UnmatchedUploadRow(
                    row=row_number,
                    asset_tag=tag,
                    reason="No asset with this asset_tag exists at the selected site.",
                    data=original,
                )
            )
            continue

        inspection_date = _parse_date(row["inspection_date"])
        if inspection_date is None:
            _add_row_error(summary, row_number, "inspection_date is blank or invalid.")
            continue
        vibration = None
        if not _is_missing(row["vibration_reading"]) and _as_text(row["vibration_reading"]):
            try:
                vibration = float(str(row["vibration_reading"]).replace(",", ".").strip())
            except (TypeError, ValueError):
                _add_row_error(summary, row_number, "vibration_reading must be numeric or blank.")
                continue
            if not math.isfinite(vibration):
                _add_row_error(summary, row_number, "vibration_reading must be a finite number or blank.")
                continue

        key = (asset.id, inspection_date)
        if key not in records_by_key:
            records_by_key[key] = db.scalar(
                select(Inspection)
                .where(Inspection.asset_id == asset.id, Inspection.inspection_date == inspection_date)
                .order_by(Inspection.id)
            )
        record = records_by_key[key]
        extra = {column: _json_safe(row[column]) for column in frame.columns if column not in explicit}
        inspector = _as_text(row["inspector_name"]) if "inspector_name" in frame.columns else None
        visual_condition = _as_text(row["visual_condition"])
        notes = _as_text(row["notes"])
        if record is None:
            record = Inspection(
                asset_id=asset.id,
                inspection_date=inspection_date,
                inspector_name=inspector or "file upload",
                vibration_reading=vibration,
                visual_condition=visual_condition,
                notes=notes,
                raw_data=extra,
            )
            db.add(record)
            records_by_key[key] = record
            summary.rows_created += 1
        else:
            if inspector:
                record.inspector_name = inspector
            if vibration is not None:
                record.vibration_reading = vibration
            if visual_condition is not None:
                record.visual_condition = visual_condition
            if notes is not None:
                record.notes = notes
            record.raw_data = _merge_json(record.raw_data, extra)
            summary.rows_updated += 1

    return _finish_upload(db, summary)


@router.post("/maintenance", response_model=UploadSummary)
def upload_maintenance(
    file: UploadFile = File(...),
    site: Site = Depends(get_authorized_site),
    db: Session = Depends(get_db),
) -> UploadSummary:
    """Create or update maintenance records; unmatched tags are skipped."""
    frame, error = _read_frame(file)
    if error or frame is None:
        return _summary_for_read_error(error or "Could not read the uploaded file.")
    invalid = _missing_columns_summary(frame, MAINTENANCE_COLUMNS)
    if invalid:
        return invalid

    summary = UploadSummary(rows_processed=len(frame.index))
    assets = db.scalars(select(Asset).where(Asset.site_id == site.id)).all()
    assets_by_tag = {_tag_key(asset.asset_tag): asset for asset in assets}
    explicit = MAINTENANCE_COLUMNS | {"performed_by"}
    records_by_key: dict[tuple[int, date], MaintenanceRecord | None] = {}

    for offset, (_, row) in enumerate(frame.iterrows()):
        row_number = offset + 2
        original = _row_dict(row)
        tag = _as_text(row["asset_tag"])
        asset = assets_by_tag.get(_tag_key(tag)) if tag else None
        if asset is None:
            summary.rows_skipped += 1
            summary.unmatched_rows.append(
                UnmatchedUploadRow(
                    row=row_number,
                    asset_tag=tag,
                    reason="No asset with this asset_tag exists at the selected site.",
                    data=original,
                )
            )
            continue

        maintenance_date = _parse_date(row["maintenance_date"])
        if maintenance_date is None:
            _add_row_error(summary, row_number, "maintenance_date is blank or invalid.")
            continue
        description = _as_text(row["description"])
        if description is None:
            _add_row_error(summary, row_number, "description must not be blank.")
            continue

        key = (asset.id, maintenance_date)
        if key not in records_by_key:
            records_by_key[key] = db.scalar(
                select(MaintenanceRecord)
                .where(
                    MaintenanceRecord.asset_id == asset.id,
                    MaintenanceRecord.maintenance_date == maintenance_date,
                )
                .order_by(MaintenanceRecord.id)
            )
        record = records_by_key[key]
        extra = {column: _json_safe(row[column]) for column in frame.columns if column not in explicit}
        performed_by = _as_text(row["performed_by"]) if "performed_by" in frame.columns else None
        if record is None:
            record = MaintenanceRecord(
                asset_id=asset.id,
                maintenance_date=maintenance_date,
                description=description,
                performed_by=performed_by,
                raw_data=extra,
            )
            db.add(record)
            records_by_key[key] = record
            summary.rows_created += 1
        else:
            record.description = description
            if performed_by is not None:
                record.performed_by = performed_by
            record.raw_data = _merge_json(record.raw_data, extra)
            summary.rows_updated += 1

    return _finish_upload(db, summary)


__all__ = ["router"]
