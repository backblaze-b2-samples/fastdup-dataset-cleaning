"""Scanner tests that exercise the deterministic issue detectors (exact-byte
duplicates + broken-file probe) without invoking fastdup. Using issue_types
that exclude near-duplicates/outliers keeps the fastdup import out of the path,
so these run on any machine."""

import io
import os
import sys
import tempfile

import pandas as pd
from PIL import Image

from app.repo import scanner


class _FakeFd:
    """Minimal fastdup handle: run() is a no-op; similarity/outliers return
    nothing so the pass yields empty results without any native work."""

    def run(self, **kwargs):
        return None

    def similarity(self):
        return None

    def outliers(self):
        return None


class _FakeFastdup:
    @staticmethod
    def create(work_dir, input_dir):
        return _FakeFd()


def _write_jpeg(path, color) -> bytes:
    img = Image.new("RGB", (32, 32), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    data = buf.getvalue()
    path.write_bytes(data)
    return data


def test_exact_duplicates_grouped_by_bytes(tmp_path):
    data = _write_jpeg(tmp_path / "a.jpg", (10, 20, 30))
    # Byte-identical copy under a different name.
    (tmp_path / "a_copy.jpg").write_bytes(data)
    _write_jpeg(tmp_path / "b.jpg", (200, 50, 50))  # distinct

    result = scanner.run_scan(str(tmp_path), "balanced", ["duplicate"])

    assert result["total_images"] == 3
    assert len(result["duplicate_groups"]) == 1
    members = set(result["duplicate_groups"][0]["members"])
    assert members == {"a.jpg", "a_copy.jpg"}
    assert result["duplicate_groups"][0]["score"] == 1.0


def test_broken_file_detected(tmp_path):
    _write_jpeg(tmp_path / "ok.jpg", (0, 128, 255))
    # Valid .jpg name, undecodable bytes.
    (tmp_path / "corrupt.jpg").write_bytes(b"\xff\xd8\xff" + b"not-an-image" * 4)

    result = scanner.run_scan(str(tmp_path), "balanced", ["broken"])

    assert result["total_images"] == 2
    broken_names = {b["local"] for b in result["broken"]}
    assert "corrupt.jpg" in broken_names
    assert "ok.jpg" not in broken_names


def test_issue_types_filter_suppresses_duplicates(tmp_path):
    data = _write_jpeg(tmp_path / "a.jpg", (10, 20, 30))
    (tmp_path / "a_copy.jpg").write_bytes(data)

    # Only ask for broken files → duplicate detection is skipped.
    result = scanner.run_scan(str(tmp_path), "balanced", ["broken"])
    assert result["duplicate_groups"] == []


def test_exact_pairs_excluded_from_near_dups_when_duplicate_deselected(
    monkeypatch, tmp_path
):
    """Regression: exact-byte duplicates must NEVER leak into the near-duplicate
    report, even when 'duplicate' is deselected. run_scan must ALWAYS compute the
    exact-byte exclusion set for the near-dup/outlier passes; only REPORTING the
    exact-duplicate section is gated by issue_types."""
    d = str(tmp_path)
    data = _write_jpeg(tmp_path / "x.jpg", (10, 20, 30))
    (tmp_path / "x_copy.jpg").write_bytes(data)  # byte-identical → exact dup
    # Distinct enough that JPEG quantization can't collapse them to identical
    # bytes (adjacent colors would, putting them in the exact-dup set).
    _write_jpeg(tmp_path / "near_a.jpg", (20, 40, 60))
    _write_jpeg(tmp_path / "near_b.jpg", (210, 170, 90))  # distinct bytes

    # fastdup reports BOTH the exact pair (dist 1.0) and a genuine near-dup pair.
    sim = pd.DataFrame(
        {
            "filename_from": [f"{d}/x.jpg", f"{d}/near_a.jpg"],
            "filename_to": [f"{d}/x_copy.jpg", f"{d}/near_b.jpg"],
            "distance": [1.0, 0.99],
        }
    )
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: d)
    fake = type(
        "_FakeFastdupMod",
        (),
        {"create": staticmethod(lambda work_dir, input_dir: _FdWithFrame(sim=sim))},
    )
    monkeypatch.setitem(sys.modules, "fastdup", fake)

    # near_duplicate requested, duplicate DESELECTED.
    result = scanner.run_scan(d, "balanced", ["near_duplicate"])

    assert result["duplicate_groups"] == []  # not reported
    near_members = {m for g in result["near_duplicate_groups"] for m in g["members"]}
    # The exact-byte pair must not appear under near-duplicates.
    assert "x.jpg" not in near_members and "x_copy.jpg" not in near_members
    assert all(g["score"] < 0.999 for g in result["near_duplicate_groups"])
    # The genuine near-duplicate pair still groups.
    assert near_members == {"near_a.jpg", "near_b.jpg"}


# --- fastdup version gate: import-time RuntimeError is prevented -------------


def test_fastdup_pass_sets_production_env_before_import(monkeypatch, tmp_path):
    """fastdup 1.85 raises at IMPORT when >10 releases behind. The pass must set
    FASTDUP_PRODUCTION=1 (which disables that network version check) so the
    import succeeds without user action."""
    monkeypatch.delenv("FASTDUP_PRODUCTION", raising=False)
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(tmp_path))
    monkeypatch.setitem(sys.modules, "fastdup", _FakeFastdup)

    near, out = scanner._fastdup_pass(str(tmp_path), ["a.jpg", "b.jpg"], 0.85, set())

    assert os.environ["FASTDUP_PRODUCTION"] == "1"
    assert near == []
    assert out == []


def test_fastdup_pass_respects_preset_production_env(monkeypatch, tmp_path):
    """setdefault must not clobber a user opting back into the version check."""
    monkeypatch.setenv("FASTDUP_PRODUCTION", "0")
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(tmp_path))
    monkeypatch.setitem(sys.modules, "fastdup", _FakeFastdup)

    scanner._fastdup_pass(str(tmp_path), ["a.jpg", "b.jpg"], 0.85, set())

    assert os.environ["FASTDUP_PRODUCTION"] == "0"


# --- fastdup 2.x column mapping: key by file PATH, not integer index ----------


class _FdWithFrame:
    """fastdup handle whose similarity()/outliers() return preset DataFrames,
    mirroring fastdup 2.x's schema (integer index columns PLUS filename_* path
    columns)."""

    def __init__(self, sim=None, out=None):
        self._sim = sim
        self._out = out

    def run(self, **kwargs):
        return None

    def similarity(self):
        return self._sim

    def outliers(self):
        return self._out


def test_near_duplicates_key_by_filename_not_index(tmp_path):
    """fastdup 2.x similarity() has bare integer `from`/`to` indices AND the real
    paths in `filename_from`/`filename_to`. Group members must be the FILENAMES
    (basenames), never the index strings, or the service can't map to B2 keys."""
    d = str(tmp_path)
    sim = pd.DataFrame(
        {
            "from": [0, 2],
            "to": [1, 3],
            "filename_from": [f"{d}/dup_a.jpg", f"{d}/pair_a.png"],
            "filename_to": [f"{d}/dup_b.jpg", f"{d}/pair_b.png"],
            "distance": [0.97, 0.91],
        }
    )
    fd = _FdWithFrame(sim=sim)

    groups = scanner._near_duplicates(fd, 0.85, set())

    all_members = {m for g in groups for m in g["members"]}
    assert all_members == {"dup_a.jpg", "dup_b.jpg", "pair_a.png", "pair_b.png"}
    # The bug (keying by index) would surface these instead.
    assert not (all_members & {"0", "1", "2", "3"})


def test_outliers_key_by_filename_not_index(tmp_path):
    """fastdup 2.x outliers() has a bare integer `outlier` index AND the real path
    in `filename_outlier`. Records must key by the FILENAME (basename)."""
    d = str(tmp_path)
    out = pd.DataFrame(
        {
            "outlier": [4, 7],
            "filename_outlier": [f"{d}/weird.jpg", f"{d}/lonely.png"],
            "distance": [0.12, 0.20],
        }
    )
    fd = _FdWithFrame(out=out)

    records = scanner._outliers(fd, set())

    names = {r["local"] for r in records}
    assert names == {"weird.jpg", "lonely.png"}
    assert not (names & {"4", "7"})
