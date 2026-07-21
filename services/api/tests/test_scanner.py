"""Scanner tests that exercise the deterministic issue detectors (exact-byte
duplicates + broken-file probe) without invoking fastdup. Using issue_types
that exclude near-duplicates/outliers keeps the fastdup import out of the path,
so these run on any machine."""

import io

from PIL import Image

from app.repo import scanner


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
