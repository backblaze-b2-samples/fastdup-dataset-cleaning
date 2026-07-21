"""B2 (S3-compatible) helpers for the curation surface.

Kept separate from ``b2_client.py`` only to respect the 300-line file limit;
both live in ``repo/`` so boto3 stays contained to the data-access layer. All
calls go through the single shared, custom-UA'd S3 client from ``b2_client``.
"""

import io
import os
import re
from pathlib import Path

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import _invalidate_list_cache, get_s3_client

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_SAFE_LOCAL = re.compile(r"[^A-Za-z0-9_.-]")


def _paginate_keys(prefix: str) -> list[dict]:
    """Return every object (dict with Key/Size) under `prefix`, paginated."""
    client = get_s3_client()
    out: list[dict] = []
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix, "MaxKeys": 1000}
    while True:
        resp = client.list_objects_v2(**kwargs)
        out.extend(resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    return out


def list_objects(prefix: str) -> list[dict]:
    """Public wrapper: list objects (Key, Size, LastModified) under a prefix."""
    try:
        return _paginate_keys(prefix)
    except ClientError as e:
        raise RuntimeError(f"B2 list failed for '{prefix}': {e}") from e


def list_immediate_prefixes(prefix: str) -> list[str]:
    """Return the immediate sub-'folders' of `prefix` via the S3 delimiter.

    e.g. list_immediate_prefixes("datasets/") -> ["datasets/demo/", ...].
    """
    client = get_s3_client()
    prefixes: list[str] = []
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Prefix": prefix,
        "Delimiter": "/",
        "MaxKeys": 1000,
    }
    try:
        while True:
            resp = client.list_objects_v2(**kwargs)
            for cp in resp.get("CommonPrefixes", []):
                prefixes.append(cp["Prefix"])
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 list-prefixes failed for '{prefix}': {e}") from e
    return prefixes


def get_object_bytes(key: str) -> bytes | None:
    """Fetch an object's bytes, or None if it does not exist."""
    client = get_s3_client()
    try:
        resp = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
        return resp["Body"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return None
        raise RuntimeError(f"B2 get failed for '{key}': {e}") from e


def presign_preview(key: str, expires_in: int = 900) -> str:
    """Presigned GET for inline rendering (image thumbnails in the gallery /
    report). No forced attachment disposition — the browser renders it in an
    <img>. Raises RuntimeError on failure."""
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.b2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 presign failed for '{key}': {e}") from e


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    """Write raw bytes to B2. Raises RuntimeError on failure."""
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=content_type,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 put failed for '{key}': {e}") from e
    _invalidate_list_cache()


def copy_object(src_key: str, dest_key: str) -> None:
    """Server-side copy within the bucket. The source is left untouched — this
    is how cleaning quarantines flagged files without ever deleting originals."""
    client = get_s3_client()
    try:
        client.copy_object(
            Bucket=settings.b2_bucket_name,
            Key=dest_key,
            CopySource={"Bucket": settings.b2_bucket_name, "Key": src_key},
        )
    except ClientError as e:
        raise RuntimeError(f"B2 copy failed '{src_key}'->'{dest_key}': {e}") from e
    _invalidate_list_cache()


def delete_prefix(prefix: str) -> int:
    """Delete every object under `prefix`. Returns the count deleted.

    Guard-railed: refuses an empty prefix so a bug can never wipe the bucket.
    Callers must pass a fully-qualified, run-scoped prefix.
    """
    if not prefix or not prefix.strip("/"):
        raise ValueError("delete_prefix requires a non-empty prefix")
    client = get_s3_client()
    objs = _paginate_keys(prefix)
    deleted = 0
    for i in range(0, len(objs), 1000):
        batch = [{"Key": o["Key"]} for o in objs[i : i + 1000]]
        if not batch:
            continue
        try:
            client.delete_objects(
                Bucket=settings.b2_bucket_name, Delete={"Objects": batch}
            )
        except ClientError as e:
            raise RuntimeError(f"B2 delete failed for '{prefix}': {e}") from e
        deleted += len(batch)
    _invalidate_list_cache()
    return deleted


def download_prefix_to_dir(prefix: str, dest_dir: str) -> dict[str, str]:
    """Stream every image object under `prefix` into `dest_dir` (flat).

    Returns a mapping of {local_filename: b2_key} so scan results (keyed by the
    local file) can be resolved back to B2 keys. Non-image objects (e.g.
    manifest.csv) are skipped. Raises RuntimeError on S3 failure.
    """
    client = get_s3_client()
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for i, obj in enumerate(_paginate_keys(prefix)):
        key = obj["Key"]
        ext = os.path.splitext(key)[1].lower()
        if ext not in _IMAGE_EXTS:
            continue
        base = _SAFE_LOCAL.sub("_", os.path.basename(key)) or "img"
        local_name = f"{i:04d}_{base}"
        local_path = os.path.join(dest_dir, local_name)
        try:
            client.download_file(settings.b2_bucket_name, key, local_path)
        except ClientError as e:
            raise RuntimeError(f"B2 download failed for '{key}': {e}") from e
        mapping[local_name] = key
    return mapping
