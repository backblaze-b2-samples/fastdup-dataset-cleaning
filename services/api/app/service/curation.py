"""Curation service: the Curation Run lifecycle (create/run, read, clean,
delete) plus dashboard aggregations.

Run state lives in B2 as status.json (running -> complete/failed) and the full
result in report.json, so listing and detail are just artifact reads and state
survives an API restart. The scan itself runs in an in-process background
thread — a single-replica design (documented in docs/RELIABILITY.md), the same
tradeoff as the in-process rate limiter and counters.
"""

import logging
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime

from app.repo import (
    copy_object,
    delete_prefix,
    download_prefix_to_dir,
    get_object_bytes,
    presign_preview,
    put_bytes,
    run_scan,
)
from app.service import datasets as ds
from app.service.report_artifacts import build_csv, build_gallery_html
from app.types import (
    ISSUE_TYPES,
    BrokenItem,
    CleanResult,
    DuplicateGroup,
    OutlierItem,
    RunStatus,
    ScanReport,
    ScanRequest,
    ScanSummary,
)

logger = logging.getLogger(__name__)

STATUS_FILE = "status.json"
REPORT_FILE = "report.json"
_JSON = "application/json"


class RunNotFoundError(Exception):
    def __init__(self, detail: str = "Scan run not found"):
        self.detail = detail
        super().__init__(detail)


class RunStateError(Exception):
    def __init__(self, detail: str = "Run is not in a valid state for this action"):
        self.detail = detail
        super().__init__(detail)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- Persistence helpers ----------------------------------------------------


def _write_status(name: str, summary: ScanSummary) -> None:
    key = ds.run_prefix(name, summary.run_id) + STATUS_FILE
    put_bytes(key, summary.model_dump_json().encode("utf-8"), _JSON)


def _read_status(name: str, run_id: str) -> ScanSummary | None:
    raw = get_object_bytes(ds.run_prefix(name, run_id) + STATUS_FILE)
    if raw is None:
        return None
    return ScanSummary.model_validate_json(raw)


def _find_run(run_id: str) -> tuple[str, ScanSummary]:
    """Locate a run across datasets by id. Bounded by the dataset count."""
    for prefix in ds.list_immediate_prefixes(ds.DATASETS_ROOT):
        name = prefix[len(ds.DATASETS_ROOT):].rstrip("/")
        if not name:
            continue
        summary = _read_status(name, run_id)
        if summary is not None:
            return name, summary
    raise RunNotFoundError()


# --- Create + run -----------------------------------------------------------


def start_scan(req: ScanRequest) -> ScanSummary:
    ds.validate_name(req.dataset)
    issue_types = [t for t in req.issue_types if t in ISSUE_TYPES] or list(ISSUE_TYPES)
    run_id = uuid.uuid4().hex[:12]
    summary = ScanSummary(
        run_id=run_id,
        dataset=req.dataset,
        label=req.label,
        sensitivity=req.sensitivity.value,
        issue_types=issue_types,
        status=RunStatus.running,
        created_at=_now(),
    )
    _write_status(req.dataset, summary)
    threading.Thread(
        target=_run_scan_thread,
        args=(req.dataset, summary),
        daemon=True,
        name=f"scan-{run_id}",
    ).start()
    return summary


def _run_scan_thread(name: str, summary: ScanSummary) -> None:
    work = tempfile.mkdtemp(prefix="dataset-scan-")
    try:
        mapping = download_prefix_to_dir(ds.raw_prefix(name), work)
        raw = run_scan(work, summary.sensitivity, summary.issue_types)
        report = _assemble_report(name, summary, raw, mapping)
        _persist_report(name, report)
        logger.info(
            "Scan complete: run=%s dataset=%s issues=%d",
            summary.run_id,
            name,
            report.issues_found,
        )
    except Exception as e:
        logger.error("Scan failed: run=%s: %s", summary.run_id, e, exc_info=True)
        summary.status = RunStatus.failed
        summary.completed_at = _now()
        summary.error = str(e)
        try:
            _write_status(name, summary)
        except Exception:
            logger.error("Could not persist failed status for %s", summary.run_id)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _groups(raw_groups: list[dict], mapping: dict[str, str]) -> list[DuplicateGroup]:
    out: list[DuplicateGroup] = []
    for i, g in enumerate(raw_groups):
        keys = [mapping[m] for m in g["members"] if m in mapping]
        if len(keys) < 2:
            continue
        keys.sort()
        out.append(
            DuplicateGroup(
                group_id=i,
                keep=keys[0],
                flagged=keys[1:],
                filenames=[k.rsplit("/", 1)[-1] for k in keys],
                score=g.get("score"),
            )
        )
    return out


def _assemble_report(
    name: str, summary: ScanSummary, raw: dict, mapping: dict[str, str]
) -> ScanReport:
    dups = _groups(raw["duplicate_groups"], mapping)
    nears = _groups(raw["near_duplicate_groups"], mapping)
    outliers = [
        OutlierItem(key=mapping[o["local"]], filename=o["local"].split("_", 1)[-1], score=o.get("score"))
        for o in raw["outliers"]
        if o["local"] in mapping
    ]
    broken = [
        BrokenItem(key=mapping[b["local"]], filename=b["local"].split("_", 1)[-1], reason=b["reason"])
        for b in raw["broken"]
        if b["local"] in mapping
    ]
    by_type = {
        "duplicate": sum(len(g.flagged) for g in dups),
        "near_duplicate": sum(len(g.flagged) for g in nears),
        "outlier": len(outliers),
        "broken": len(broken),
    }
    report = ScanReport(
        **summary.model_dump(
            exclude={
                "status",
                "completed_at",
                "issues_found",
                "issues_by_type",
                "total_images",
            }
        ),
        status=RunStatus.complete,
        completed_at=_now(),
        total_images=raw["total_images"],
        issues_found=sum(by_type.values()),
        issues_by_type=by_type,
        duplicates=dups,
        near_duplicates=nears,
        outliers=outliers,
        broken=broken,
    )
    return report


def _persist_report(name: str, report: ScanReport) -> None:
    base = ds.run_prefix(name, report.run_id)
    # preview_urls are generated fresh on read (they expire) — don't store them.
    stored = report.model_copy(update={"preview_urls": {}})
    put_bytes(base + REPORT_FILE, stored.model_dump_json().encode("utf-8"), _JSON)
    put_bytes(base + "report.csv", build_csv(report), "text/csv")
    urls = {k: presign_preview(k) for k in _flagged_keys(report)}
    put_bytes(base + "gallery.html", build_gallery_html(report, urls), "text/html")
    _write_status(name, _summary_of(report))


def _summary_of(report: ScanReport) -> ScanSummary:
    return ScanSummary(**report.model_dump(include=set(ScanSummary.model_fields)))


def _flagged_keys(report: ScanReport) -> list[str]:
    """Keys the run will quarantine: flagged group members (never the kept
    representative) plus every outlier and broken file."""
    keys: list[str] = []
    for g in report.duplicates + report.near_duplicates:
        keys.extend(g.flagged)
    keys.extend(o.key for o in report.outliers)
    keys.extend(b.key for b in report.broken)
    return keys


# --- Read -------------------------------------------------------------------


def list_runs() -> list[ScanSummary]:
    runs: list[ScanSummary] = []
    for prefix in ds.list_immediate_prefixes(ds.DATASETS_ROOT):
        name = prefix[len(ds.DATASETS_ROOT):].rstrip("/")
        if not name:
            continue
        for obj in ds.list_objects(ds.reports_prefix(name)):
            if obj["Key"].endswith("/" + STATUS_FILE):
                raw = get_object_bytes(obj["Key"])
                if raw:
                    runs.append(ScanSummary.model_validate_json(raw))
    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


def get_run(run_id: str) -> ScanReport:
    name, summary = _find_run(run_id)
    if summary.status != RunStatus.complete:
        # running/failed: no report yet — surface the header only.
        return ScanReport(**summary.model_dump(include=set(ScanSummary.model_fields)))
    raw = get_object_bytes(ds.run_prefix(name, run_id) + REPORT_FILE)
    if raw is None:
        return ScanReport(**summary.model_dump(include=set(ScanSummary.model_fields)))
    report = ScanReport.model_validate_json(raw)
    # Overlay the authoritative cleaned state from status.json (report.json is frozen).
    report.cleaned = summary.cleaned
    report.quarantined_count = summary.quarantined_count
    # Preview each group's kept representative too, so the "keep" tile renders.
    keeps = [g.keep for g in report.duplicates + report.near_duplicates]
    report.preview_urls = {k: presign_preview(k) for k in keeps + _flagged_keys(report)}
    return report


# --- Clean + delete ---------------------------------------------------------


def clean_run(run_id: str) -> CleanResult:
    name, summary = _find_run(run_id)
    if summary.status != RunStatus.complete:
        raise RunStateError("Only a completed run can be cleaned")
    if summary.cleaned:
        return CleanResult(
            run_id=run_id,
            quarantined_count=summary.quarantined_count,
            manifest_key=ds.manifest_key(name, run_id),
            already_cleaned=True,
        )
    report = get_run(run_id)
    flagged = _flagged_keys(report)
    quar = ds.quarantine_prefix(name)
    lines = ["action,key"]
    for key in flagged:
        copy_object(key, quar + key.rsplit("/", 1)[-1])  # server-side copy; original untouched
        lines.append(f"quarantined,{key}")
    manifest = ds.manifest_key(name, run_id)
    put_bytes(manifest, ("\n".join(lines) + "\n").encode("utf-8"), "text/csv")
    summary.cleaned = True
    summary.quarantined_count = len(flagged)
    _write_status(name, summary)
    return CleanResult(run_id=run_id, quarantined_count=len(flagged), manifest_key=manifest)


def delete_run(run_id: str) -> None:
    name, _ = _find_run(run_id)
    # Prefix-scoped to exactly this run's artifacts (CLAUDE.local.md safety).
    delete_prefix(ds.run_prefix(name, run_id))
