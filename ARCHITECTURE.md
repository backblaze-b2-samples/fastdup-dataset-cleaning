<!-- last_verified: 2026-07-15 -->
# Architecture

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - Dashboard with stats, upload chart, recent uploads
  - File upload with drag-and-drop, progress tracking
  - File browser with preview, download, delete
  - Dark mode via `next-themes`
- **services/api/** — FastAPI backend (layered architecture)
  - REST API for file upload, listing, deletion
  - B2 S3 integration via boto3
  - File metadata extraction (images, PDFs)
  - Health check endpoint with B2 connectivity verification
  - Structured JSON logging with request tracing
  - Prometheus-format metrics endpoint
- **packages/shared/** — TypeScript type definitions
  - Mirrors Pydantic models from the API
  - Consumed by `apps/web/` as workspace dependency

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access (boto3 B2 client) — no business logic
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3` only allowed in `repo/` layer
4. All boundary data uses Pydantic models (no raw dicts across layers)
5. Each file stays under 300 lines

### Directory Structure

```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models (FileMetadata, UploadStats, etc.)
    config/                Settings loaded from environment
    repo/                  B2 S3 client (data access layer)
    service/               Business logic (upload, files, metadata)
    runtime/               FastAPI route handlers
  tests/                   pytest tests (structural + integration)
```

## Boundary Invariants

- **No external SDK leakage**: `boto3` is only imported in `app/repo/`. All other layers interact with B2 through the repo interface.
- **No raw dicts at boundaries**: All data crossing layer boundaries uses typed Pydantic models.
- **No cross-layer mutable state**: Configuration is read-only after init, and no mutable state is shared *between* layers. Intra-layer caches/counters (the listing cache in `repo/b2_client.py`, the download counter in `repo/counter.py`, the rate-limit and metrics state in `runtime/`) are module-local and guarded by a `threading.Lock`.
- **Validated inputs**: All HTTP inputs validated by FastAPI/Pydantic. File keys reject empty and path-traversal patterns; optional prefix confinement via `ALLOWED_KEY_PREFIX` (off by default).

## Deployment

- **Local dev** — `pnpm dev` runs both services via `concurrently`
  - Web: `localhost:3000`
  - API: `localhost:8000`
- **Railway** — two services from the same repo
  - See `infra/railway/README.md` for configuration

## Data Stores

- **Backblaze B2** — object storage (S3-compatible API), the sole data store (no database)
  - Datasets: `datasets/<name>/raw/` (images)
  - Run artifacts: `datasets/<name>/quality-reports/<run-id>/` (`status.json`, `report.json`,
    `report.csv`, `gallery.html`) — run state and results live here, not in a DB
  - Quarantine: `datasets/<name>/quarantine/` (+ `datasets/<name>/manifests/cleaned-<run-id>.csv`)
  - Generic uploads: `uploads/` (kept starter surface)
  - Listing/discovery via S3 `list_objects_v2` (+ `Delimiter` for dataset prefixes)

## External Services

- **Backblaze B2 S3 API** — dataset + artifact storage, retrieval, server-side copy, presigned URLs
- **fastdup** (local, in-process) — image dataset quality analysis on CPU. Not a network
  service and needs no API key; imported only in `repo/scanner.py`.

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API** — CORS-restricted to configured origins. `CORSMiddleware` is registered LAST in `main.py` (outermost) so it wraps **every** response, including uncaught-exception 500s — otherwise the browser would block error responses and the UI would only see an opaque "network error". See [docs/RELIABILITY.md](docs/RELIABILITY.md#error-handling). A per-IP rate-limit middleware sits inner to CORS; see [docs/SECURITY.md](docs/SECURITY.md#rate-limiting).
- **API -> B2** — authenticated via application keys, signature v4
- **Client -> B2** — presigned URLs for download (10-min expiry, forced attachment)

## Data Flows

### Curation (this app's primary feature)

- **Scan (create + run)**: Browser -> `POST /scans {dataset, sensitivity, issue_types, label?}`
  -> `service/curation.start_scan` writes `status.json` (`running`) to B2 and spawns an
  **in-process background thread**, returning `202` immediately. The thread:
  1. streams the dataset's images from `datasets/<name>/raw/` to a **local temp working dir**
     via the S3 API (`repo.download_prefix_to_dir`),
  2. runs `repo/scanner.run_scan` — fastdup fingerprints on CPU; exact-byte dups by content
     hash; broken files by a Pillow decode probe,
  3. writes `report.json`, `report.csv`, `gallery.html`, and an updated `status.json`
     (`complete`) under `datasets/<name>/quality-reports/<run-id>/`,
  4. deletes the temp dir.
  On any failure the thread writes `status.json` (`failed`) with the error. The frontend polls
  `GET /scans/{run_id}` every 2s while `running`.
- **Read**: `GET /scans` lists runs by reading each `status.json`; `GET /scans/{run_id}`
  returns the parsed `report.json` and mints fresh presigned preview URLs for the flagged keys.
- **Clean (apply)**: Browser -> `POST /scans/{run_id}/clean` -> service copies each flagged
  object to `datasets/<name>/quarantine/` via **server-side `copy_object`** (originals are
  never deleted), writes a cleaned manifest, and marks the run `cleaned`.
- **Delete run**: Browser -> `DELETE /scans/{run_id}` -> service deletes **only** the
  `datasets/<name>/quality-reports/<run-id>/` prefix (guard-railed against an empty prefix).
- **Datasets**: `GET /datasets` discovers dataset prefixes with the S3 delimiter;
  `GET /datasets/{name}` lists `raw/` images and presigns each for the gallery.

Run state lives entirely in B2 (`status.json` / `report.json`), so listings and detail are
just artifact reads and state survives an API restart. This is also the artifact-store story.

### Kept starter flows

- **Upload**: Browser -> `POST /upload` (multipart) -> API validates -> service orchestrates -> repo writes to B2 -> metadata extracted -> response
- **List**: Browser -> `GET /files` -> service calls repo -> returns file list
- **Download**: Browser -> `GET /files/{key}/download` -> service validates key -> repo generates presigned URL -> browser downloads
- **Delete**: Browser -> `DELETE /files/{key}` -> service validates key -> repo deletes from B2

## Observability

- Structured JSON logging on all requests with `request_id`
- Request timing middleware (logs duration per request; also the catch-all that converts uncaught exceptions to a typed JSON 500)
- `/metrics` endpoint (Prometheus format: request count, latency, upload count)
- `/health` endpoint (B2 connectivity check)

## Canonical Files

- Layered API handler: `services/api/app/runtime/upload.py`
- Service orchestration: `services/api/app/service/upload.py`
- B2 data access (repo layer): `services/api/app/repo/b2_client.py`
- Pydantic models: `services/api/app/types/` (`files.py`, `upload.py`, `stats.py`, `formatting.py`)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`
- Frontend API client: `apps/web/src/lib/api-client.ts`
- Shared TypeScript types: `packages/shared/src/types.ts`

## Core Features

- [Dataset Quality Scan](docs/features/dataset-scan.md)
- [Curation Runs & Report Artifacts](docs/features/curation-runs.md)
- [Safe Cleaning (Quarantine)](docs/features/dataset-cleaning.md)
- [Datasets Explorer](docs/features/datasets-explorer.md)
- [Dashboard](docs/features/dashboard.md)
- [File Upload](docs/features/file-upload.md) (kept from starter)
- [File Browser](docs/features/file-browser.md) (kept from starter)
- [Metadata Extraction](docs/features/metadata-extraction.md) (kept from starter)

## References

- [docs/SECURITY.md](docs/SECURITY.md) — security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md) — reliability expectations
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions
