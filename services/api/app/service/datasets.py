"""Datasets service: lists datasets under the app's own `datasets/` prefix and
builds the per-dataset image gallery (presigned thumbnails + quality flags).

Also the single source of truth for the B2 key layout every curation artifact
uses — `service/curation.py` imports these builders so the prefix scheme is
defined in exactly one place.
"""

import os
import re

from app.repo import (
    list_immediate_prefixes,
    list_objects,
    presign_preview,
)
from app.types import DatasetDetail, DatasetImage, DatasetSummary
from app.types.formatting import humanize_bytes

DATASETS_ROOT = "datasets/"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class DatasetNameError(Exception):
    """Raised when a dataset name is missing or unsafe."""

    def __init__(self, detail: str = "Invalid dataset name"):
        self.detail = detail
        super().__init__(detail)


class DatasetNotFoundError(Exception):
    def __init__(self, detail: str = "Dataset not found"):
        self.detail = detail
        super().__init__(detail)


# --- Key layout (the one place prefixes are defined) ------------------------


def validate_name(name: str) -> None:
    if not name or not _NAME_RE.match(name):
        raise DatasetNameError()


def dataset_prefix(name: str) -> str:
    return f"{DATASETS_ROOT}{name}/"


def raw_prefix(name: str) -> str:
    return f"{DATASETS_ROOT}{name}/raw/"


def reports_prefix(name: str) -> str:
    return f"{DATASETS_ROOT}{name}/quality-reports/"


def run_prefix(name: str, run_id: str) -> str:
    return f"{DATASETS_ROOT}{name}/quality-reports/{run_id}/"


def quarantine_prefix(name: str) -> str:
    return f"{DATASETS_ROOT}{name}/quarantine/"


def manifest_key(name: str, run_id: str) -> str:
    return f"{DATASETS_ROOT}{name}/manifests/cleaned-{run_id}.csv"


# --- Queries ----------------------------------------------------------------


def _is_image(key: str) -> bool:
    return os.path.splitext(key)[1].lower() in _IMAGE_EXTS


def raw_image_objects(name: str) -> list[dict]:
    """Every image object under datasets/<name>/raw/."""
    return [o for o in list_objects(raw_prefix(name)) if _is_image(o["Key"])]


def quarantined_basenames(name: str) -> set[str]:
    """Basenames of files currently under the dataset's quarantine/ prefix."""
    return {
        os.path.basename(o["Key"])
        for o in list_objects(quarantine_prefix(name))
        if _is_image(o["Key"])
    }


def list_datasets() -> list[DatasetSummary]:
    summaries: list[DatasetSummary] = []
    for prefix in list_immediate_prefixes(DATASETS_ROOT):
        name = prefix[len(DATASETS_ROOT):].rstrip("/")
        if not name:
            continue
        images = raw_image_objects(name)
        size = sum(o["Size"] for o in images)
        summaries.append(
            DatasetSummary(
                name=name,
                image_count=len(images),
                size_bytes=size,
                size_human=humanize_bytes(size),
            )
        )
    summaries.sort(key=lambda d: d.name)
    return summaries


def get_dataset(name: str) -> DatasetDetail:
    validate_name(name)
    images = raw_image_objects(name)
    if not images:
        # An empty/absent dataset is a 404 rather than a misleading empty gallery.
        raise DatasetNotFoundError()
    quarantined = quarantined_basenames(name)
    items: list[DatasetImage] = []
    for o in sorted(images, key=lambda x: x["Key"]):
        key = o["Key"]
        base = os.path.basename(key)
        items.append(
            DatasetImage(
                key=key,
                filename=base,
                url=presign_preview(key),
                quarantined=base in quarantined,
            )
        )
    return DatasetDetail(
        name=name,
        image_count=len(items),
        quarantined_count=sum(1 for i in items if i.quarantined),
        images=items,
    )
