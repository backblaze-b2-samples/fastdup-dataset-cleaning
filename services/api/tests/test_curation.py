"""Curation service tests: scan lifecycle, safe cleaning (copy-not-delete),
prefix-scoped delete, and dataset listing — all with the scanner and B2 repo
mocked so no network or fastdup is required."""

import pytest

from app.repo import b2_curation
from app.service import curation
from app.service import datasets as ds
from app.types import RunStatus, ScanRequest, ScanSummary, Sensitivity

# --- Scan lifecycle: run thread assembles + persists a report ---------------


def test_run_scan_thread_persists_complete_report(monkeypatch):
    puts: dict[str, bytes] = {}
    monkeypatch.setattr(
        curation, "download_prefix_to_dir", lambda prefix, work: {
            "0001_a.jpg": "datasets/demo/raw/a.jpg",
            "0002_a_copy.jpg": "datasets/demo/raw/a_copy.jpg",
            "0003_broken.jpg": "datasets/demo/raw/broken.jpg",
        }
    )
    monkeypatch.setattr(
        curation, "run_scan", lambda work, sens, types: {
            "total_images": 3,
            "broken": [{"local": "0003_broken.jpg", "reason": "cannot decode"}],
            "duplicate_groups": [{"members": ["0001_a.jpg", "0002_a_copy.jpg"], "score": 1.0}],
            "near_duplicate_groups": [],
            "outliers": [],
        }
    )
    monkeypatch.setattr(curation, "put_bytes", lambda key, data, ct: puts.__setitem__(key, data))
    monkeypatch.setattr(curation, "presign_preview", lambda key: f"https://signed/{key}")

    summary = ScanSummary(
        run_id="run123",
        dataset="demo",
        label="first",
        sensitivity="balanced",
        issue_types=["duplicate", "near_duplicate", "outlier", "broken"],
        status=RunStatus.running,
        created_at="2026-07-21T00:00:00+00:00",
    )
    curation._run_scan_thread("demo", summary)

    base = "datasets/demo/quality-reports/run123/"
    assert base + "report.json" in puts
    assert base + "report.csv" in puts
    assert base + "gallery.html" in puts
    assert base + "status.json" in puts

    report = curation.ScanReport.model_validate_json(puts[base + "report.json"])
    assert report.status == RunStatus.complete
    assert report.total_images == 3
    # 1 flagged duplicate + 1 broken = 2 issues.
    assert report.issues_found == 2
    assert report.issues_by_type["duplicate"] == 1
    assert report.issues_by_type["broken"] == 1
    assert report.duplicates[0].keep == "datasets/demo/raw/a.jpg"
    assert report.duplicates[0].flagged == ["datasets/demo/raw/a_copy.jpg"]


def test_run_scan_thread_marks_failed_on_error(monkeypatch):
    puts: dict[str, bytes] = {}
    monkeypatch.setattr(
        curation, "download_prefix_to_dir",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("B2 down")),
    )
    monkeypatch.setattr(curation, "put_bytes", lambda key, data, ct: puts.__setitem__(key, data))

    summary = ScanSummary(
        run_id="runfail",
        dataset="demo",
        sensitivity="balanced",
        issue_types=["duplicate"],
        status=RunStatus.running,
        created_at="2026-07-21T00:00:00+00:00",
    )
    curation._run_scan_thread("demo", summary)

    status = ScanSummary.model_validate_json(
        puts["datasets/demo/quality-reports/runfail/status.json"]
    )
    assert status.status == RunStatus.failed
    assert "B2 down" in (status.error or "")


def test_start_scan_writes_running_status(monkeypatch):
    puts: dict[str, bytes] = {}
    monkeypatch.setattr(curation, "put_bytes", lambda key, data, ct: puts.__setitem__(key, data))
    monkeypatch.setattr(curation, "_run_scan_thread", lambda *a, **k: None)  # don't run

    summary = curation.start_scan(
        ScanRequest(dataset="demo", sensitivity=Sensitivity.strict, issue_types=["duplicate"])
    )
    assert summary.status == RunStatus.running
    key = f"datasets/demo/quality-reports/{summary.run_id}/status.json"
    assert key in puts


# --- get_run: preview URLs + authoritative cleaned-state overlay ------------


def _complete_report(**overrides) -> "curation.ScanReport":
    base = dict(
        run_id="run123",
        dataset="demo",
        sensitivity="balanced",
        issue_types=["duplicate", "broken"],
        status=RunStatus.complete,
        created_at="2026-07-21T00:00:00+00:00",
        total_images=3,
        issues_found=2,
        duplicates=[
            curation.DuplicateGroup(
                group_id=0,
                keep="datasets/demo/raw/a.jpg",
                flagged=["datasets/demo/raw/a_copy.jpg"],
                filenames=["a.jpg", "a_copy.jpg"],
                score=1.0,
            )
        ],
        broken=[
            curation.BrokenItem(
                key="datasets/demo/raw/broken.jpg", filename="broken.jpg", reason="x"
            )
        ],
    )
    base.update(overrides)
    return curation.ScanReport(**base)


def test_get_run_preview_urls_cover_keep_and_flagged(monkeypatch):
    # Finding 2: the kept representative of each group must get a preview URL too
    # (it was omitted before, so the "keep" tile rendered broken).
    report = _complete_report()
    summary = ScanSummary(**report.model_dump(include=set(ScanSummary.model_fields)))
    monkeypatch.setattr(curation, "_find_run", lambda run_id: ("demo", summary))
    monkeypatch.setattr(
        curation, "get_object_bytes", lambda key: report.model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(curation, "presign_preview", lambda key: f"https://signed/{key}")

    result = curation.get_run("run123")

    assert "datasets/demo/raw/a.jpg" in result.preview_urls  # keep
    assert "datasets/demo/raw/a_copy.jpg" in result.preview_urls  # flagged
    assert "datasets/demo/raw/broken.jpg" in result.preview_urls  # broken


def test_get_run_overlays_cleaned_state_from_status(monkeypatch):
    # Finding 3: report.json is frozen at assembly time (cleaned=False), but
    # status.json is the authoritative post-clean state — get_run must overlay it.
    report = _complete_report(cleaned=False, quarantined_count=0)
    summary = ScanSummary(**report.model_dump(include=set(ScanSummary.model_fields)))
    summary.cleaned = True
    summary.quarantined_count = 4
    monkeypatch.setattr(curation, "_find_run", lambda run_id: ("demo", summary))
    monkeypatch.setattr(
        curation, "get_object_bytes", lambda key: report.model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(curation, "presign_preview", lambda key: "https://signed")

    result = curation.get_run("run123")

    assert result.cleaned is True
    assert result.quarantined_count == 4


# --- Safe cleaning: copy to quarantine, never delete ------------------------


def test_clean_run_copies_flagged_never_deletes(monkeypatch):
    copies: list[tuple[str, str]] = []
    puts: dict[str, bytes] = {}
    report = curation.ScanReport(
        run_id="run123",
        dataset="demo",
        sensitivity="balanced",
        issue_types=["duplicate", "broken"],
        status=RunStatus.complete,
        created_at="2026-07-21T00:00:00+00:00",
        total_images=3,
        issues_found=2,
        duplicates=[
            curation.DuplicateGroup(
                group_id=0,
                keep="datasets/demo/raw/a.jpg",
                flagged=["datasets/demo/raw/a_copy.jpg"],
                filenames=["a.jpg", "a_copy.jpg"],
                score=1.0,
            )
        ],
        broken=[curation.BrokenItem(key="datasets/demo/raw/broken.jpg", filename="broken.jpg", reason="x")],
    )
    summary = ScanSummary(**report.model_dump(include=set(ScanSummary.model_fields)))

    monkeypatch.setattr(curation, "_find_run", lambda run_id: ("demo", summary))
    monkeypatch.setattr(curation, "get_run", lambda run_id: report)
    monkeypatch.setattr(curation, "copy_object", lambda src, dst: copies.append((src, dst)))
    monkeypatch.setattr(curation, "put_bytes", lambda key, data, ct: puts.__setitem__(key, data))

    result = curation.clean_run("run123")

    assert result.quarantined_count == 2
    assert len(copies) == 2
    # Every copy targets the dataset's quarantine/ prefix; sources are the originals.
    for src, dst in copies:
        assert dst.startswith("datasets/demo/quarantine/")
        assert src.startswith("datasets/demo/raw/")
    # A cleaned manifest is written; originals are never deleted (no delete call exists).
    assert result.manifest_key == "datasets/demo/manifests/cleaned-run123.csv"
    assert result.manifest_key in puts


def test_clean_run_rejects_incomplete(monkeypatch):
    summary = ScanSummary(
        run_id="r", dataset="demo", sensitivity="balanced", issue_types=["duplicate"],
        status=RunStatus.running, created_at="2026-07-21T00:00:00+00:00",
    )
    monkeypatch.setattr(curation, "_find_run", lambda run_id: ("demo", summary))
    with pytest.raises(curation.RunStateError):
        curation.clean_run("r")


# --- Prefix-scoped delete ---------------------------------------------------


def test_delete_run_is_prefix_scoped(monkeypatch):
    deleted: list[str] = []
    summary = ScanSummary(
        run_id="run123", dataset="demo", sensitivity="balanced", issue_types=["duplicate"],
        status=RunStatus.complete, created_at="2026-07-21T00:00:00+00:00",
    )
    monkeypatch.setattr(curation, "_find_run", lambda run_id: ("demo", summary))
    monkeypatch.setattr(curation, "delete_prefix", lambda prefix: deleted.append(prefix))

    curation.delete_run("run123")

    # Scoped to exactly this run's artifact prefix — never the whole dataset/bucket.
    assert deleted == ["datasets/demo/quality-reports/run123/"]


def test_delete_prefix_guard_rejects_empty():
    with pytest.raises(ValueError):
        b2_curation.delete_prefix("")


# --- Dataset listing --------------------------------------------------------


def test_list_datasets_summarizes_images(monkeypatch):
    monkeypatch.setattr(ds, "list_immediate_prefixes", lambda root: ["datasets/demo/"])
    monkeypatch.setattr(
        ds, "list_objects",
        lambda prefix: [
            {"Key": "datasets/demo/raw/a.jpg", "Size": 100},
            {"Key": "datasets/demo/raw/b.png", "Size": 200},
            {"Key": "datasets/demo/raw/manifest.txt", "Size": 5},  # non-image, ignored
        ],
    )
    summaries = ds.list_datasets()
    assert len(summaries) == 1
    assert summaries[0].name == "demo"
    assert summaries[0].image_count == 2
    assert summaries[0].size_bytes == 300
