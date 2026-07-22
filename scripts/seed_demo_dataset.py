#!/usr/bin/env python3
"""Seed a small synthetic demo dataset into B2 for the fastdup scan to find.

Generates ~20 images at runtime with Pillow (no committed binaries) and uploads
them to `datasets/demo/raw/` using the same B2_* env vars as the API. The set is
crafted so a scan has real issues to surface:

  * 3 EXACT duplicates  — identical bytes under different names
  * 2 NEAR-duplicates   — a base image with a barely-perceptible brightness shift (re-encoded)
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
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

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


def _color(rng, lo: int = 30, hi: int = 226) -> tuple[int, int, int]:
    """A deterministic RGB colour drawn from the per-image RNG."""
    return tuple(int(c) for c in rng.integers(lo, hi, size=3))


# --- Composition primitives -------------------------------------------------
# fastdup's visual embeddings are largely colour-invariant and group by
# composition/structure, so every base image must have a DIFFERENT dominant
# shape — otherwise they all fingerprint as near-identical and collapse into one
# runaway near-duplicate cluster. Each drawer takes the per-image RNG so
# positions/sizes/counts/colours vary while staying fully deterministic in `i`.


def _centered_rectangle(draw, rng, w, h):
    m = int(rng.integers(24, 44))
    draw.rectangle([m, m, w - m, h - m], fill=_color(rng, 120))


def _triangle(draw, rng, w, h):
    draw.polygon([(w // 2, 12), (12, h - 12), (w - 12, h - 12)], fill=_color(rng, 120))


def _circle_cluster(draw, rng, w, h):
    for _ in range(int(rng.integers(5, 9))):
        cx, cy = int(rng.integers(24, w - 24)), int(rng.integers(24, h - 24))
        r = int(rng.integers(10, 22))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_color(rng, 120))


def _horizontal_bars(draw, rng, w, h):
    n = int(rng.integers(4, 8))
    bh = max(1, h // (2 * n))
    for i in range(n):
        y = i * 2 * bh
        draw.rectangle([0, y, w, y + bh], fill=_color(rng, 120))


def _vertical_bars(draw, rng, w, h):
    n = int(rng.integers(4, 8))
    bw = max(1, w // (2 * n))
    for i in range(n):
        x = i * 2 * bw
        draw.rectangle([x, 0, x + bw, h], fill=_color(rng, 120))


def _checkerboard(draw, rng, w, h):
    n = int(rng.integers(4, 7))
    cw, ch = w // n, h // n
    fg = _color(rng, 120)
    for r in range(n):
        for c in range(n):
            if (r + c) % 2 == 0:
                draw.rectangle([c * cw, r * ch, (c + 1) * cw, (r + 1) * ch], fill=fg)


def _concentric_rings(draw, rng, w, h):
    cx, cy = w // 2, h // 2
    for r in range(w // 2 - 6, 6, -14):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_color(rng, 120), width=4)


def _scattered_dots(draw, rng, w, h):
    for _ in range(int(rng.integers(30, 60))):
        cx, cy = int(rng.integers(4, w - 4)), int(rng.integers(4, h - 4))
        r = int(rng.integers(2, 5))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_color(rng, 120))


def _big_glyph(draw, rng, w, h):
    letter = chr(int(rng.integers(65, 91)))  # A-Z
    font = ImageFont.load_default(size=120)  # size arg: Pillow >= 10.1 (repo pins 10.3)
    draw.text((w // 2, h // 2), letter, fill=_color(rng, 150), font=font, anchor="mm")


def _diagonal_split(draw, rng, w, h):
    draw.polygon([(0, 0), (w, 0), (0, h)], fill=_color(rng, 120))


def _offcenter_ellipse(draw, rng, w, h):
    cx, cy = int(rng.integers(40, w - 40)), int(rng.integers(40, h - 40))
    rx, ry = int(rng.integers(30, 60)), int(rng.integers(30, 60))
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=_color(rng, 120))


def _plus_cross(draw, rng, w, h):
    t = int(rng.integers(20, 36))
    fg = _color(rng, 120)
    draw.rectangle([0, h // 2 - t, w, h // 2 + t], fill=fg)
    draw.rectangle([w // 2 - t, 0, w // 2 + t, h], fill=fg)


def _starburst(draw, rng, w, h):
    cx, cy = w // 2, h // 2
    for _ in range(int(rng.integers(10, 18))):
        ex, ey = int(rng.integers(0, w)), int(rng.integers(0, h))
        draw.line([(cx, cy), (ex, ey)], fill=_color(rng, 120), width=3)


def _nested_frames(draw, rng, w, h):
    for m in range(6, w // 2 - 6, 14):
        draw.rectangle([m, m, w - m, h - m], outline=_color(rng, 120), width=3)


# One drawer per base image: 14 structurally-distinct layouts, no two sharing a
# dominant shape (see the note above on why colour alone is not enough).
_LAYOUTS = [
    _centered_rectangle,
    _triangle,
    _circle_cluster,
    _horizontal_bars,
    _vertical_bars,
    _checkerboard,
    _concentric_rings,
    _scattered_dots,
    _big_glyph,
    _diagonal_split,
    _offcenter_ellipse,
    _plus_cross,
    _starburst,
    _nested_frames,
]


def _compose(i: int) -> Image.Image:
    """Build the i-th base image: a dark-ish background plus one distinct
    primitive layout, fully deterministic in `i` (seeded RNG). No two base
    images share a dominant structure, so fastdup treats them as genuinely
    different rather than collapsing them into one near-duplicate cluster."""
    rng = np.random.default_rng(i)
    img = Image.new("RGB", SIZE, _color(rng, 0, 70))  # dark bg so shapes read
    draw = ImageDraw.Draw(img)
    _LAYOUTS[i % len(_LAYOUTS)](draw, rng, SIZE[0], SIZE[1])
    return img


def _jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _near_variant(img: Image.Image) -> Image.Image:
    """Build a genuine near-duplicate: the SAME image with a barely-perceptible
    +2% brightness shift (as if re-exported at slightly different exposure).
    It is visually near-identical to a human and embeds at fastdup similarity
    ~0.998 — far above the ~0.84 similarity ceiling of the structurally-distinct
    base images — so it groups cleanly with its base while nothing distinct
    chains in.

    (History: an earlier gaussian-noise perturbation, std=6, was far too
    aggressive for these low-complexity synthetic shapes. It dropped similarity
    to ~0.79-0.83 — below even the loose threshold AND inside the distinct-image
    cross-link band — so the near-duplicate stage found ZERO groups at every
    sensitivity. A gentle brightness shift keeps the embedding essentially
    unchanged, which is what a real near-duplicate looks like.)"""
    return ImageEnhance.Brightness(img).enhance(1.02)


def main() -> None:
    client, bucket = _client()
    uploads: list[tuple[str, bytes]] = []

    # 14 distinct base images — each a different primitive layout (see _compose).
    base: dict[str, bytes] = {}
    for i in range(14):
        data = _jpeg_bytes(_compose(i))
        name = f"img_{i:02d}.jpg"
        base[name] = data
        uploads.append((name, data))

    # 3 exact duplicates — identical bytes under new names.
    for i in range(3):
        src = f"img_{i:02d}.jpg"
        uploads.append((f"img_{i:02d}_dup.jpg", base[src]))

    # 2 near-duplicates — same base image with a barely-perceptible brightness
    # shift, re-encoded. Genuine near-dups (fastdup similarity ~0.998).
    for i in (3, 4):
        src_img = Image.open(io.BytesIO(base[f"img_{i:02d}.jpg"]))
        uploads.append((f"img_{i:02d}_near.jpg", _jpeg_bytes(_near_variant(src_img))))

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
