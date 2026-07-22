<!-- last_verified: 2026-07-21 -->
# App Workflows

User journeys inside the application. The core loop is: **ingest → scan → report → clean**.

## Run a dataset quality scan

- User navigates to `/scans` and clicks **New scan** (or Dashboard → New scan)
- On `/scans/new`:
  - **Dataset** — a selector populated from `GET /datasets` (defaults to the seeded `demo`)
  - **Sensitivity** — a selector: Strict (0.92) / Balanced (0.90) / Loose (0.88); Balanced default
  - **Issue types** — checkboxes: Exact duplicates, Near-duplicates, Outliers, Broken files (all on)
  - **Label** — optional free-text name
- Submitting `POST /scans` starts a background run and redirects to `/scans/[runId]`
- The detail page shows `running` with a spinner and polls until the scan completes
- See: [Dataset Quality Scan](features/dataset-scan.md)

## Review a scan report

- On `/scans/[runId]`, a completed run shows summary stats (dataset, sensitivity, images, issues)
- Flagged images are grouped by issue type — Exact duplicates, Near-duplicates, Outliers,
  Broken files — with real thumbnails (presigned URLs)
- Duplicate groups mark the **kept** image vs the ones to quarantine
- See: [Curation Runs](features/curation-runs.md)

## Apply cleaning (quarantine)

- On a completed run, click **Apply cleaning**
- `POST /scans/{run_id}/clean` copies every flagged file to `datasets/<name>/quarantine/`
  (server-side copy — originals in `raw/` are never deleted) and writes a cleaned manifest
- A toast confirms how many files were quarantined; the run is marked `cleaned`
- See: [Dataset Cleaning](features/dataset-cleaning.md)

## Delete a run

- On a run's report, click **Delete** and confirm
- `DELETE /scans/{run_id}` removes only that run's `quality-reports/<run-id>/` artifacts;
  dataset images and quarantined files are untouched

## Browse datasets

- User navigates to `/datasets` → grid of datasets (name, image count, size)
- Opening one shows `/datasets/[name]` — a gallery of the actual images with quarantine flags
- See: [Datasets Explorer](features/datasets-explorer.md)

## View the dashboard

- User navigates to `/` (home)
- Stat cards: datasets, images, issues found, files quarantined
- Issues-by-type chart (latest completed run per dataset) + recent scans table
- See: [Dashboard](features/dashboard.md)

## Kept starter journeys

- **Upload** (`/upload`) — generic drag-and-drop upload to `uploads/`. See [File Upload](features/file-upload.md).
- **Browse the whole bucket** (`/files`) — full-bucket tree with preview/download/delete.
  See [File Browser](features/file-browser.md).
