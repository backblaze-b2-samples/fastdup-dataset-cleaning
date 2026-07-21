import logging
import re

# Sync `def` handlers run in Starlette's threadpool (blocking boto3) — see
# runtime/files.py. POST /scans returns immediately after spawning the
# background run thread; the run's progress is read back from B2 status.json.
from fastapi import APIRouter, HTTPException

from app.service.curation import (
    RunNotFoundError,
    RunStateError,
    clean_run,
    delete_run,
    get_run,
    list_runs,
    start_scan,
)
from app.service.datasets import DatasetNameError
from app.types import CleanResult, ScanReport, ScanRequest, ScanSummary

logger = logging.getLogger(__name__)

router = APIRouter()

# run_ids are 12-char uuid hex; validate before using one to build a B2 prefix.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9]{6,64}$")


def _valid_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run id")
    return run_id


@router.post("/scans", response_model=ScanSummary, status_code=202)
def create_scan_endpoint(req: ScanRequest):
    try:
        return start_scan(req)
    except DatasetNameError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None


@router.get("/scans", response_model=list[ScanSummary])
def list_scans_endpoint():
    return list_runs()


@router.get("/scans/{run_id}", response_model=ScanReport)
def get_scan_endpoint(run_id: str):
    try:
        return get_run(_valid_run_id(run_id))
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.post("/scans/{run_id}/clean", response_model=CleanResult)
def clean_scan_endpoint(run_id: str):
    try:
        result = clean_run(_valid_run_id(run_id))
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except RunStateError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None
    logger.info("Run cleaned: run=%s quarantined=%d", run_id, result.quarantined_count)
    return result


@router.delete("/scans/{run_id}")
def delete_scan_endpoint(run_id: str):
    try:
        delete_run(_valid_run_id(run_id))
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    logger.info("Run deleted: run=%s", run_id)
    return {"deleted": True, "run_id": run_id}
