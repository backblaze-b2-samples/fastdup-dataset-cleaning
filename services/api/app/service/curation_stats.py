"""Dashboard aggregations for the curation surface. Split out of
service/curation.py to keep that module under the file-size limit."""

from app.service import datasets as ds
from app.service.curation import list_runs
from app.types import ISSUE_TYPES, CurationStats, IssueTypeCount, RunStatus, ScanSummary


def _latest_complete_per_dataset() -> list[ScanSummary]:
    """The most recent completed run per dataset — so re-running a scan doesn't
    double-count issues in the dashboard totals."""
    latest: dict[str, ScanSummary] = {}
    for r in list_runs():
        if r.status != RunStatus.complete:
            continue
        cur = latest.get(r.dataset)
        if cur is None or r.created_at > cur.created_at:
            latest[r.dataset] = r
    return list(latest.values())


def get_stats() -> CurationStats:
    summaries = ds.list_datasets()
    latest = _latest_complete_per_dataset()
    quarantined = sum(len(ds.quarantined_basenames(s.name)) for s in summaries)
    return CurationStats(
        datasets=len(summaries),
        images=sum(s.image_count for s in summaries),
        issues_found=sum(r.issues_found for r in latest),
        quarantined=quarantined,
    )


def get_issue_type_counts() -> list[IssueTypeCount]:
    totals = dict.fromkeys(ISSUE_TYPES, 0)
    for r in _latest_complete_per_dataset():
        for t, c in r.issues_by_type.items():
            if t in totals:
                totals[t] += c
    return [IssueTypeCount(issue_type=t, count=totals[t]) for t in ISSUE_TYPES]
