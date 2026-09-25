from typing import Any

from pydantic import BaseModel, Field


class UploadError(BaseModel):
    """A file-level or row-level issue found while importing an upload."""

    row: int | None = None
    message: str


class UnmatchedUploadRow(BaseModel):
    """Source row whose asset tag could not be matched to a site asset."""

    row: int
    asset_tag: str | None = None
    reason: str
    data: dict[str, Any]


class UploadSummary(BaseModel):
    """Counts and row details returned after processing a CSV or XLSX upload."""

    rows_processed: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    unmatched_rows: list[UnmatchedUploadRow] = Field(default_factory=list)
    errors: list[UploadError] = Field(default_factory=list)
