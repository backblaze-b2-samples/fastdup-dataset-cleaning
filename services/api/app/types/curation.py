"""Types for the curation surface: datasets, scans (curation runs), and reports.

A *curation run* is one fastdup scan over one dataset. Its state and artifacts
live in B2 (status.json + report.json), so listing/detail are just artifact
reads and state survives an API restart.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

# The four issue categories fastdup surfaces. Kept as string values so they
# serialize directly into report/status JSON and map 1:1 to the UI checkboxes.
ISSUE_TYPES = ("duplicate", "near_duplicate", "outlier", "broken")


class Sensitivity(StrEnum):
    strict = "strict"
    balanced = "balanced"
    loose = "loose"


class RunStatus(StrEnum):
    running = "running"
    complete = "complete"
    failed = "failed"


# --- Datasets ---------------------------------------------------------------


class DatasetSummary(BaseModel):
    name: str
    image_count: int
    size_bytes: int
    size_human: str


class DatasetImage(BaseModel):
    key: str
    filename: str
    url: str | None = None  # presigned preview URL (short-lived)
    quarantined: bool = False


class DatasetDetail(BaseModel):
    name: str
    image_count: int
    quarantined_count: int
    images: list[DatasetImage]


# --- Scan request / lifecycle ----------------------------------------------


class ScanRequest(BaseModel):
    dataset: str
    sensitivity: Sensitivity = Sensitivity.balanced
    issue_types: list[str] = Field(default_factory=lambda: list(ISSUE_TYPES))
    label: str | None = None


class ScanSummary(BaseModel):
    """Lightweight run header parsed from status.json (backs the /scans list)."""

    run_id: str
    dataset: str
    label: str | None = None
    sensitivity: str
    issue_types: list[str]
    status: RunStatus
    created_at: str
    completed_at: str | None = None
    total_images: int = 0
    issues_found: int = 0
    issues_by_type: dict[str, int] = Field(default_factory=dict)
    cleaned: bool = False
    quarantined_count: int = 0
    error: str | None = None


# --- Report detail ----------------------------------------------------------


class DuplicateGroup(BaseModel):
    group_id: int
    keep: str  # object key kept as the canonical copy
    flagged: list[str]  # object keys to quarantine (all but `keep`)
    filenames: list[str]
    score: float | None = None


class OutlierItem(BaseModel):
    key: str
    filename: str
    score: float | None = None


class BrokenItem(BaseModel):
    key: str
    filename: str
    reason: str


class ScanReport(ScanSummary):
    duplicates: list[DuplicateGroup] = Field(default_factory=list)
    near_duplicates: list[DuplicateGroup] = Field(default_factory=list)
    outliers: list[OutlierItem] = Field(default_factory=list)
    broken: list[BrokenItem] = Field(default_factory=list)
    # Object keys resolved to presigned preview URLs for the report gallery.
    preview_urls: dict[str, str] = Field(default_factory=dict)


# --- Cleaning + dashboard ---------------------------------------------------


class CleanResult(BaseModel):
    run_id: str
    quarantined_count: int
    manifest_key: str
    already_cleaned: bool = False


class IssueTypeCount(BaseModel):
    issue_type: str
    count: int


class CurationStats(BaseModel):
    datasets: int
    images: int
    issues_found: int
    quarantined: int
