<!-- last_verified: 2026-07-21 -->
# Feature: Curation Runs & Report Artifacts

## Purpose
Make every scan a durable, inspectable *Curation Run* whose state and full report are stored
as artifacts in B2 — so runs can be listed, reopened, cleaned, and deleted, and survive an
API restart with no database.

## Used By
- UI: `/scans` (list), `/scans/[runId]` (detail/report)
- API: `GET /scans`, `GET /scans/{run_id}`, `DELETE /scans/{run_id}`

## Core Functions
- `services/api/app/service/curation.py` — `list_runs()`, `get_run()`, `delete_run()`, `_find_run()`
- `services/api/app/service/report_artifacts.py` — `build_csv()`, `build_gallery_html()`
- `apps/web/src/components/scans/scans-list.tsx`, `scan-report.tsx`
- `apps/web/src/lib/queries.ts` — `useScans()`, `useScan()` (polls while running), `useDeleteScan()`

## Canonical Files
- Run lifecycle: `services/api/app/service/curation.py`
- Report view: `apps/web/src/components/scans/scan-report.tsx`

## Primary entity: Curation Run
- **create/run**: `POST /scans` (see [dataset-scan.md](dataset-scan.md))
- **read**: `GET /scans` (from each `status.json`) + `GET /scans/{run_id}` (parsed `report.json`)
- **clean**: `POST /scans/{run_id}/clean` (see [dataset-cleaning.md](dataset-cleaning.md))
- **delete**: `DELETE /scans/{run_id}` — removes only this run's `quality-reports/<run-id>/` prefix
- **edit**: omitted by design — a run is an immutable record of a scan at a point in time. To
  re-curate with different settings, start a new run. (`omitted_ui_verbs: edit`.)

## Artifacts written per run (under `datasets/<name>/quality-reports/<run-id>/`)
- `status.json` — lightweight run header (`running` → `complete`/`failed`); backs the list
- `report.json` — full result (issue groups + flagged keys); backs the detail view
- `report.csv` — one row per flagged file (+ each dup group's kept representative)
- `gallery.html` — static HTML overview with thumbnails (presigned links, time-limited)

## Inputs
- run_id: str (path param; validated `^[A-Za-z0-9]{6,64}$` before use in a prefix)

## Outputs
- `GET /scans` → `ScanSummary[]` (newest first)
- `GET /scans/{run_id}` → `ScanReport` (issue detail + fresh presigned `preview_urls`)
- `DELETE /scans/{run_id}` → `{deleted: true, run_id}`

## Flow
- List: iterate dataset prefixes → read every `.../quality-reports/*/status.json`
- Detail: locate the run, read `report.json`, mint fresh presigned preview URLs for flagged keys
- Preview URLs are **not** stored (they expire); they are generated on read

## Edge Cases
- Unknown run_id → 404
- Run still `running`/`failed` → detail returns the header only (no report body yet)
- Media must actually render: the detail view uses real `<img>` from presigned URLs

## UX States
- Empty: "No scans yet"
- Loading: skeletons; a `running` run polls every 2s and advances on completion
- Error: 404 → "Scan not found"; other errors → retry

## Verification
- Test files: `services/api/tests/test_curation.py`
- Required cases: run persistence, prefix-scoped delete, failed-run status
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: run lifecycle + delete-scope tests green

## Related Docs
- [Dataset Scan](dataset-scan.md)
- [Dataset Cleaning](dataset-cleaning.md)
- [docs/SECURITY.md](../SECURITY.md)
- [docs/RELIABILITY.md](../RELIABILITY.md)
