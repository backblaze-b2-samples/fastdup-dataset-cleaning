<!-- last_verified: 2026-07-21 -->
# Feature: Dataset Quality Scan

## Purpose
Find quality issues in an image dataset stored in B2 — exact duplicates, near-duplicates,
outliers, and broken/corrupt files — using fastdup, locally on CPU, with no external API key.

## Used By
- UI: `/scans/new` (start), `/scans/[runId]` (report)
- API: `POST /scans`, `GET /scans/{run_id}`
- Job: in-process background thread per run (`service/curation._run_scan_thread`)

## Core Functions
- `services/api/app/repo/scanner.py` — `run_scan()`; the **only** module that imports fastdup
- `services/api/app/repo/b2_curation.py` — `download_prefix_to_dir()` streams images to a temp dir
- `services/api/app/service/curation.py` — `start_scan()`, `_run_scan_thread()`, `_assemble_report()`

## Canonical Files
- Scan engine: `services/api/app/repo/scanner.py`

## Inputs
- dataset: str (selector, from `GET /datasets`)
- sensitivity: `strict` (0.90) / `balanced` (0.85) / `loose` (0.80) — maps to the fastdup near-duplicate similarity threshold
- issue_types: subset of `duplicate`, `near_duplicate`, `outlier`, `broken`
- label: optional free-text run name

## Outputs
- A curation run whose artifacts are written to `datasets/<name>/quality-reports/<run-id>/`
- Side effects: reads dataset images from B2; writes `status.json`, `report.json`, `report.csv`, `gallery.html`

## Flow
- `POST /scans` writes `status.json` (`running`) and spawns a background thread, returns `202`
- Thread streams `datasets/<name>/raw/` to a local temp dir (S3 `get_object`/`download_file`)
- `run_scan()`:
  - broken files → Pillow decode probe (undecodable = broken)
  - exact duplicates → group by SHA-256 of the bytes (deterministic)
  - near-duplicates + outliers → **fastdup** (`fastdup.create(...).run(threshold=...)`), parsed
    from its similarity/outliers output; exact-dup pairs are excluded from near-dup grouping
- Report artifacts + `status.json` (`complete`) are written to B2; the temp dir is deleted
- Frontend polls `GET /scans/{run_id}` every 2s while `running`

## Edge Cases
- fastdup import/run failure → run is marked `failed` with the error (never silently mocked)
- Fewer than 2 valid images → fastdup pass is skipped (nothing to compare)
- Non-image objects (e.g. `manifest.csv`) → skipped during download
- **CPU-only:** fastdup uses an ONNX CPU runtime; there is no GPU path to autodetect, so the
  scan defaults to and stays on CPU (never requires a GPU).
- **macOS arm64 caveat:** fastdup's native wheel can be flaky on Apple Silicon. If it hangs or
  fails to import, run the backend in a native `linux/arm64` Python container (same precedent
  as other native-wheel samples). The scan code path is unchanged.

## Scaling note (documented deviation)
For the demo, the scan streams the dataset's images to a local temp working dir because
fastdup computes visual fingerprints from local files — it does not read bytes over the
network. At true million-image scale you would shard the dataset and stream in batches; the
code path stays identical. This keeps the sample honest rather than pretending fastdup reads
directly from B2.

## UX States
- Empty: no datasets → prompt to seed
- Loading: run shows `running` with a spinner; report auto-advances on completion
- Error: `failed` runs show the error message

## Verification
- Test files: `services/api/tests/test_scanner.py`, `services/api/tests/test_curation.py`
- Required cases: exact-dup grouping, broken detection, issue-type filtering, run lifecycle (assemble + persist), failed-run handling
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: scanner + curation tests green; a real scan of the `demo` dataset produces a report with issues

## Related Docs
- [Curation Runs](curation-runs.md)
- [Dataset Cleaning](dataset-cleaning.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
