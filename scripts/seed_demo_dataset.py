#!/usr/bin/env python3
"""Seed a small synthetic demo dataset into B2 for the fastdup scan to find.

Generates ~20 images at runtime with Pillow (no committed binaries) and uploads
them to `datasets/demo/raw/` using the same B2_* env vars as the API. The set is
crafted so a scan has real issues to surface:

  * 3 EXACT duplicates  — identical bytes under different names
  * 2 NEAR-duplicates   — a base image plus light gaussian noise (re-encoded)
  * 1 BROKEN file       — a .jpg name whose bytes are truncated/garbage

Idempotent: re-running overwrites the same keys. All demo data stays under the
`datasets/demo/` prefix (shared-bucket safety).

Usage (from repo root, backend venv active):
    python scripts/seed_demo_dataset.py
"""

import io
import os
import sys
from pathlib import Path

import boto3
import numpy as np
from botocore.config import Config
from dotenv import load_dotenv
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DATASET = "demo"
RAW_PREFIX = f"datasets/{DATASET}/raw/"
USER_AGENT = "b2ai-fastdup-dataset-cleaning"
SIZE = (160, 160)


def _client():
    key_id = os.environ.get("B2_APPLICATION_KEY_ID", "")
    app_key = os.environ.get("B2_APPLICATION_KEY", "")
    bucket = os.environ.get("B2_BUCKET_NAME", "")
    region = os.environ.get("B2_REGION", "")
    missing = [
        name
        for name, val in (
            ("B2_APPLICATION_KEY_ID", key_id),
            ("B2_APPLICATION_KEY", app_key),
            ("B2_BUCKET_NAME", bucket),
            ("B2_REGION", region),
        )
        if not val
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)} (see .env.example)")
        sys.exit(1)
    client = boto3.client(
        "s3",
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
        config=Config(signature_version="s3v4", user_agent_extra=USER_AGENT),
    )
    return client, bucket


def _gradient(hue: int) -> Image.Image:
    """A distinct diagonal-gradient image, seeded by `hue` for variety."""
    img = Image.new("RGB", SIZE)
    draw = ImageDraw.Draw(img)
    w, h = SIZE
    for y in range(h):
        r = (hue * 7 + y) % 256
        g = (hue * 13 + y * 2) % 256
        b = (hue * 29 + y // 2) % 256
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    # A shape so images aren't pure gradients (helps fastdup fingerprints).
    draw.ellipse([w // 4, h // 4, 3 * w // 4, 3 * h // 4], outline=(255, 255, 255), width=3)
    draw.text((6, 6), f"#{hue}", fill=(255, 255, 255))
    return img


def _jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _add_noise(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).astype(np.int16)
    noise = np.random.default_rng(42).normal(0, 6, arr.shape).astype(np.int16)
    noisy = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy, "RGB")


def main() -> None:
    client, bucket = _client()
    uploads: list[tuple[str, bytes]] = []

    # 14 distinct base images.
    base: dict[str, bytes] = {}
    for i in range(14):
        data = _jpeg_bytes(_gradient(i * 17 + 3))
        name = f"img_{i:02d}.jpg"
        base[name] = data
        uploads.append((name, data))

    # 3 exact duplicates — identical bytes under new names.
    for i in range(3):
        src = f"img_{i:02d}.jpg"
        uploads.append((f"img_{i:02d}_dup.jpg", base[src]))

    # 2 near-duplicates — same base image + light noise, re-encoded.
    for i in (3, 4):
        src_img = Image.open(io.BytesIO(base[f"img_{i:02d}.jpg"]))
        uploads.append((f"img_{i:02d}_near.jpg", _jpeg_bytes(_add_noise(src_img))))

    # 1 broken file — valid JPEG SOI marker then garbage, so Pillow can't decode.
    uploads.append(("broken_00.jpg", b"\xff\xd8\xff" + os.urandom(512)))

    manifest = ["path,label"]
    for name, data in uploads:
        key = RAW_PREFIX + name
        content_type = "image/jpeg"
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        label = (
            "broken"
            if name.startswith("broken")
            else "duplicate"
            if "_dup" in name
            else "near_duplicate"
            if "_near" in name
            else "clean"
        )
        manifest.append(f"{name},{label}")
        print(f"  uploaded {key} ({len(data)} bytes)")

    manifest_key = f"datasets/{DATASET}/manifest.csv"
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=("\n".join(manifest) + "\n").encode("utf-8"),
        ContentType="text/csv",
    )
    print(f"\nSeeded {len(uploads)} images + manifest to datasets/{DATASET}/ in bucket '{bucket}'.")
    print("Open the app, go to Scans → New scan, and scan the 'demo' dataset.")


if __name__ == "__main__":
    main()
