"""fastdup adapter — the dataset-quality scan engine.

This is the ONLY module that imports fastdup (mirrors the "contain external
SDKs in repo/" invariant that keeps boto3 in repo/ too). fastdup runs locally
on CPU via an ONNX runtime; there is no GPU code path to select, so this scan
is CPU-only by construction and never requires a GPU (satisfies the
local-deployment rule — nothing to autodetect).

The visual work — near-duplicate similarity and outlier detection — is done by
fastdup for real. Exact-byte duplicates are grouped by content hash (a
deterministic, correct signal fastdup's float distances can't guarantee) and
broken/corrupt files are found with a Pillow decode probe. All three feed one
combined report.
"""

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Similarity threshold per sensitivity preset. Higher = stricter (only very
# similar pairs are flagged as near-duplicates).
SENSITIVITY_THRESHOLD = {
    "strict": 0.90,
    "balanced": 0.85,
    "loose": 0.80,
}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _list_images(image_dir: str) -> list[str]:
    return sorted(
        f
        for f in os.listdir(image_dir)
        if os.path.splitext(f)[1].lower() in _IMAGE_EXTS
    )


def _detect_broken(image_dir: str, files: list[str]) -> tuple[list[dict], list[str]]:
    """Return (broken_records, valid_files). A file is broken if Pillow can't
    decode it. Broken files are excluded from the fastdup pass."""
    from PIL import Image

    broken: list[dict] = []
    valid: list[str] = []
    for name in files:
        path = os.path.join(image_dir, name)
        try:
            with Image.open(path) as img:
                img.verify()  # header/decode check without loading pixels
            valid.append(name)
        except Exception as e:
            broken.append({"local": name, "reason": str(e) or "cannot decode image"})
    return broken, valid


def _hash_duplicates(image_dir: str, files: list[str]) -> tuple[list[dict], set[str]]:
    """Group files with identical bytes (exact duplicates). Returns the groups
    and the set of files that are in a >1 duplicate group (to exclude from
    near-duplicate detection so an exact dup isn't double-counted)."""
    by_hash: dict[str, list[str]] = {}
    for name in files:
        with open(os.path.join(image_dir, name), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        by_hash.setdefault(digest, []).append(name)
    groups: list[dict] = []
    in_group: set[str] = set()
    for members in by_hash.values():
        if len(members) > 1:
            groups.append({"members": sorted(members), "score": 1.0})
            in_group.update(members)
    return groups, in_group


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _first_col(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def _fastdup_pass(
    image_dir: str, valid: list[str], threshold: float, exact_dupes: set[str]
) -> tuple[list[dict], list[dict]]:
    """Run fastdup and derive near-duplicate groups + outliers.

    Returns (near_duplicate_groups, outlier_records). Both empty when fastdup
    finds nothing. A genuine fastdup import/run error propagates to the caller
    (the run is then honestly marked failed) rather than being swallowed.
    """
    import tempfile

    import fastdup

    work_dir = tempfile.mkdtemp(prefix="fastdup-work-")
    fd = fastdup.create(work_dir=work_dir, input_dir=image_dir)
    fd.run(threshold=threshold, overwrite=True, print_summary=False)

    near_groups = _near_duplicates(fd, threshold, exact_dupes)
    outliers = _outliers(fd, exact_dupes)
    return near_groups, outliers


def _near_duplicates(fd, threshold: float, exact_dupes: set[str]) -> list[dict]:
    try:
        sim = fd.similarity()
    except Exception:
        logger.warning("fastdup similarity() unavailable", exc_info=True)
        return []
    if sim is None or len(sim) == 0:
        return []
    cols = list(sim.columns)
    c_from = _first_col(cols, ["from", "filename_from", "img_from"])
    c_to = _first_col(cols, ["to", "filename_to", "img_to"])
    c_dist = _first_col(cols, ["distance", "score"])
    if not c_from or not c_to:
        return []

    uf = _UnionFind()
    scores: dict[str, float] = {}
    for _, row in sim.iterrows():
        a, b = os.path.basename(str(row[c_from])), os.path.basename(str(row[c_to]))
        if a == b:
            continue
        dist = float(row[c_dist]) if c_dist else 1.0
        if c_dist and dist < threshold:
            continue
        # Skip pairs that are exact-byte duplicates (already reported).
        if a in exact_dupes and b in exact_dupes:
            continue
        uf.union(a, b)
        key = uf.find(a)
        scores[key] = min(scores.get(key, 1.0), dist)

    comps: dict[str, set[str]] = {}
    for node in list(uf.parent):
        comps.setdefault(uf.find(node), set()).add(node)
    groups: list[dict] = []
    for root, members in comps.items():
        real = sorted(m for m in members if m not in exact_dupes)
        if len(real) > 1:
            groups.append({"members": real, "score": round(scores.get(root, 0.0), 4)})
    return groups


def _outliers(fd, exact_dupes: set[str]) -> list[dict]:
    try:
        out = fd.outliers()
    except Exception:
        logger.warning("fastdup outliers() unavailable", exc_info=True)
        return []
    if out is None or len(out) == 0:
        return []
    cols = list(out.columns)
    c_from = _first_col(cols, ["outlier", "from", "filename_outlier", "filename_from"])
    c_dist = _first_col(cols, ["distance", "score"])
    if not c_from:
        return []
    seen: set[str] = set()
    records: list[dict] = []
    for _, row in out.iterrows():
        name = os.path.basename(str(row[c_from]))
        if name in seen or name in exact_dupes:
            continue
        seen.add(name)
        score = round(float(row[c_dist]), 4) if c_dist else None
        records.append({"local": name, "score": score})
    return records[:50]


def run_scan(image_dir: str, sensitivity: str, issue_types: list[str]) -> dict:
    """Scan a local directory of images and return structured issues keyed by
    local filename. Caller (service) resolves local names to B2 keys."""
    threshold = SENSITIVITY_THRESHOLD.get(sensitivity, 0.85)
    files = _list_images(image_dir)

    broken: list[dict] = []
    valid = files
    if "broken" in issue_types:
        broken, valid = _detect_broken(image_dir, files)
    else:
        _, valid = _detect_broken(image_dir, files)  # still exclude undecodable

    exact_groups: list[dict] = []
    exact_set: set[str] = set()
    if "duplicate" in issue_types:
        exact_groups, exact_set = _hash_duplicates(image_dir, valid)

    near_groups: list[dict] = []
    outliers: list[dict] = []
    want_near = "near_duplicate" in issue_types
    want_out = "outlier" in issue_types
    if (want_near or want_out) and len(valid) >= 2:
        near_all, out_all = _fastdup_pass(image_dir, valid, threshold, exact_set)
        near_groups = near_all if want_near else []
        outliers = out_all if want_out else []

    return {
        "total_images": len(files),
        "broken": broken,
        "duplicate_groups": exact_groups,
        "near_duplicate_groups": near_groups,
        "outliers": outliers,
    }
