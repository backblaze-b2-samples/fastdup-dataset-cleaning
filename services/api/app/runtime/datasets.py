import logging

# Sync `def` handlers: the whole chain is blocking boto3, so Starlette runs
# these in its threadpool (see runtime/files.py for the rationale).
from fastapi import APIRouter, HTTPException

from app.service.datasets import (
    DatasetNameError,
    DatasetNotFoundError,
    get_dataset,
    list_datasets,
)
from app.types import DatasetDetail, DatasetSummary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets_endpoint():
    return list_datasets()


@router.get("/datasets/{name}", response_model=DatasetDetail)
def get_dataset_endpoint(name: str):
    try:
        return get_dataset(name)
    except DatasetNameError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
