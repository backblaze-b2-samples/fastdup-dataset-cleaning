import logging

# Sync `def` handlers run in Starlette's threadpool (blocking boto3) — see
# runtime/files.py.
from fastapi import APIRouter

from app.service.curation_stats import get_issue_type_counts, get_stats
from app.types import CurationStats, IssueTypeCount

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/curation/stats", response_model=CurationStats)
def curation_stats_endpoint():
    return get_stats()


@router.get("/curation/stats/issues", response_model=list[IssueTypeCount])
def curation_issue_counts_endpoint():
    return get_issue_type_counts()
