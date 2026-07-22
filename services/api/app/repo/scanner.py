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
# similar pairs are even *considered* a near-duplicate link). fastdup's visual
# embeddings are largely colour-invariant and group by composition/structure, so
# the structurally-distinct base images cross-link only up to ~0.84, while a
# genuine near-duplicate (the same image with a barely-perceptible perturbation)
# embeds at ~0.998. Every threshold sits in that clean gap, so genuine near-dups
# always group at balanced+loose and no distinct pair is ever even considered.
SENSITIVITY_THRESHOLD = {
    "strict": 0.92,
    "balanced": 0.90,
    "loose": 0.88,
}

# Extra similarity, on top of the sensitivity threshold, that a pair must clear
# before it may MERGE two images into the same near-duplicate group. This is the
# anti-chaining safeguard: _near_duplicates() groups with single-linkage
# union-find, so without it one loosely-similar (~threshold) cross-link chains
# many structurally-distinct images into one runaway group. Genuine
# near-duplicates score ~0.998 and clear threshold+margin at every sensitivity;
# marginal cross-links between distinct images (<=~0.84) do not.
NEAR_DUP_GROUP_MARGIN = 0.05

# Cap on the merge floor so a genuine near-duplicate still merges even at the
# strictest sensitivity (strict 0.92 + margin 0.05 = 0.97 uncapped; capping at
# 0.95 keeps the floor safely below the ~0.998 genuine-near-dup similarity).
NEAR_DUP_GROUP_FLOOR_MAX = 0.95

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

    # Some fastdup builds run a "you're on an old version" check AT IMPORT that
    # queries pypi and RAISES a RuntimeError when the installed release is >10
    # behind the latest and the network is reachable — so `import fastdup` itself
    # would fail. Opting into production mode disables that network version gate;
    # the engine works fine otherwise. `setdefault` lets a user still force the
    # check by exporting FASTDUP_PRODUCTION=0. Must run BEFORE the import to take
    # effect. Kept as future-proofing even on 2.x (harmless when no gate fires).
    os.environ.setdefault("FASTDUP_PRODUCTION", "1")
    import fastdup

    work_dir = tempfile.mkdtemp(prefix="fastdup-work-")
    fd = fastdup.create(work_dir=work_dir, input_dir=image_dir)
    fd.run(threshold=threshold, overwrite=True, print_summary=False)

    near_groups = _near_duplicates(fd, threshold, exact_dupes)
    # An image that belongs to a near-duplicate group must not ALSO be reported as
    # an outlier (contradictory, and it double-counts the file). Exclude near-dup
    # members from the outlier pass, mirroring the exact-duplicate exclusion.
    near_members = {m for g in near_groups for m in g["members"]}
    outliers = _outliers(fd, exact_dupes | near_members)
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
    # fastdup 2.x returns the actual file PATHS in filename_from/filename_to and
    # bare integer row INDICES in from/to. Prefer the path columns so records key
    # by filename (the service maps those to B2 keys); index columns are the
    # fallback for older/alternate schemas.
    c_from = _first_col(cols, ["filename_from", "img_from", "from"])
    c_to = _first_col(cols, ["filename_to", "img_to", "to"])
    c_dist = _first_col(cols, ["distance", "score"])
    if not c_from or not c_to:
        return []

    # Anti-chaining merge floor: a pair may MERGE two images into the same
    # near-duplicate group only when it clears threshold+margin (capped by
    # NEAR_DUP_GROUP_FLOOR_MAX so genuine ~0.998 near-dupes still merge at the
    # strictest sensitivity), not merely `threshold`. `threshold` alone still
    # gates whether a pair is even *considered* a near-duplicate link.
    merge_floor = min(threshold + NEAR_DUP_GROUP_MARGIN, NEAR_DUP_GROUP_FLOOR_MAX)

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
        # Only merge when the pair clears the anti-chaining floor; a marginal
        # (~threshold) cross-link between distinct images must not chain them
        # into one runaway group.
        if c_dist and dist < merge_floor:
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
    # fastdup 2.x puts the outlier file PATH in filename_outlier and a bare
    # integer row INDEX in outlier. Prefer the path columns (see _near_duplicates).
    c_from = _first_col(cols, ["filename_outlier", "filename_from", "outlier", "from"])
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

    want_dup = "duplicate" in issue_types
    want_near = "near_duplicate" in issue_types
    want_out = "outlier" in issue_types

    # The exact-byte hash grouping serves two independent roles: it is the
    # REPORTED "exact duplicates" section (only when the user asked for it) AND
    # the exclusion set that keeps byte-identical pairs out of the near-duplicate
    # / outlier passes. That exclusion must apply ALWAYS — a byte-identical pair
    # must never leak into Near-duplicates just because "duplicate" wasn't in
    # issue_types. So compute the grouping whenever any of the three passes needs
    # it, but only surface the groups in the report when "duplicate" is requested.
    exact_groups: list[dict] = []
    exact_set: set[str] = set()
    if want_dup or want_near or want_out:
        groups, exact_set = _hash_duplicates(image_dir, valid)
        if want_dup:
            exact_groups = groups

    near_groups: list[dict] = []
    outliers: list[dict] = []
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
