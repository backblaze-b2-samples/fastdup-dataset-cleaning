"""Builders for the non-JSON scan artifacts written to B2: report.csv and
gallery.html. Kept out of service/curation.py to respect the file-size limit.
Pure functions — no I/O, no boto3 — so they're trivially unit-testable.
"""

import csv
import html
import io

from app.types import ScanReport


def build_csv(report: ScanReport) -> bytes:
    """One row per flagged file, plus the kept representative of each dup group."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["issue_type", "group_id", "role", "key", "filename", "score", "reason"])
    for label, groups in (("duplicate", report.duplicates), ("near_duplicate", report.near_duplicates)):
        for g in groups:
            for i, key in enumerate([g.keep, *g.flagged]):
                role = "keep" if key == g.keep and i == 0 else "flagged"
                fn = g.filenames[i] if i < len(g.filenames) else key.rsplit("/", 1)[-1]
                w.writerow([label, g.group_id, role, key, fn, g.score or "", ""])
    for o in report.outliers:
        w.writerow(["outlier", "", "flagged", o.key, o.filename, o.score or "", ""])
    for b in report.broken:
        w.writerow(["broken", "", "flagged", b.key, b.filename, "", b.reason])
    return buf.getvalue().encode("utf-8")


def _thumb(key: str, urls: dict[str, str]) -> str:
    url = urls.get(key)
    label = html.escape(key.rsplit("/", 1)[-1])
    if not url:
        return f'<figure><div class="ph"></div><figcaption>{label}</figcaption></figure>'
    return (
        f'<figure><img loading="lazy" src="{html.escape(url)}" alt="{label}">'
        f"<figcaption>{label}</figcaption></figure>"
    )


def build_gallery_html(report: ScanReport, urls: dict[str, str]) -> bytes:
    """Static HTML overview of the flagged images. Thumbnails use presigned
    URLs captured at build time, so they expire — the JSON/CSV are the durable
    record; this is a human-friendly snapshot."""
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>Quality report — {html.escape(report.dataset)} / {html.escape(report.run_id)}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;background:#0b0d12;color:#e6e8ee}"
        "h1{font-size:1.4rem}h2{margin-top:2rem;font-size:1.1rem;border-bottom:1px solid #2a2f3a;padding-bottom:.3rem}"
        ".grid{display:flex;flex-wrap:wrap;gap:1rem;margin-top:1rem}"
        "figure{margin:0;width:150px}img,.ph{width:150px;height:150px;object-fit:cover;border-radius:8px;background:#1a1e27}"
        "figcaption{font-size:.72rem;color:#9aa3b2;margin-top:.3rem;word-break:break-all}"
        ".note{color:#9aa3b2;font-size:.85rem}</style></head><body>",
        f"<h1>Quality report: {html.escape(report.dataset)}</h1>",
        f"<p class='note'>Run {html.escape(report.run_id)} — sensitivity "
        f"{html.escape(report.sensitivity)} — {report.total_images} images scanned, "
        f"{report.issues_found} issues found. Thumbnails are time-limited presigned links.</p>",
    ]

    def section(title: str, keys: list[str]) -> None:
        parts.append(f"<h2>{html.escape(title)} ({len(keys)})</h2><div class='grid'>")
        parts.extend(_thumb(k, urls) for k in keys)
        parts.append("</div>")

    section("Exact duplicates", [k for g in report.duplicates for k in g.flagged])
    section("Near-duplicates", [k for g in report.near_duplicates for k in g.flagged])
    section("Outliers", [o.key for o in report.outliers])
    section("Broken files", [b.key for b in report.broken])
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")
