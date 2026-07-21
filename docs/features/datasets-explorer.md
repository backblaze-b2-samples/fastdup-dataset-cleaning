<!-- last_verified: 2026-07-21 -->
# Feature: Datasets Explorer

## Purpose
Browse the image datasets this app manages — scoped to its own `datasets/` prefix — and, for
a chosen dataset, see a gallery of the actual images (real thumbnails) with quality flags.
This is the app-scoped counterpart to the kept full-bucket File browser (`/files`).

## Used By
- UI: `/datasets` (list), `/datasets/[name]` (gallery)
- API: `GET /datasets`, `GET /datasets/{name}`

## Core Functions
- `services/api/app/service/datasets.py` — `list_datasets()`, `get_dataset()`, key-layout builders
- `services/api/app/repo/b2_curation.py` — `list_immediate_prefixes()`, `list_objects()`, `presign_preview()`
- `apps/web/src/components/datasets/datasets-list.tsx`, `dataset-gallery.tsx`
- `apps/web/src/components/scans/thumbnail.tsx` — presigned `<img>` tile
- `apps/web/src/lib/queries.ts` — `useDatasets()`, `useDataset()`

## Canonical Files
- Dataset queries: `services/api/app/service/datasets.py`
- Gallery: `apps/web/src/components/datasets/dataset-gallery.tsx`

## Inputs
- name: str (path param; validated `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)

## Outputs
- `GET /datasets` → `DatasetSummary[]` (name, image_count, size_bytes, size_human)
- `GET /datasets/{name}` → `DatasetDetail` (images with presigned `url` + `quarantined` flag)

## Flow
- List: discover dataset prefixes under `datasets/` with the S3 delimiter; count/size each `raw/`
- Detail: list `datasets/<name>/raw/` images, presign each for inline rendering, and flag any
  whose basename currently appears under `datasets/<name>/quarantine/`

## Edge Cases
- Dataset with no images → 404 (rather than a misleading empty gallery)
- Non-image objects under `raw/` → ignored
- Presigned thumbnails expire — they are minted per request and rendered as real `<img>`

## UX States
- Empty: "No datasets yet" → prompt to run the seed script
- Loading: thumbnail skeleton grid
- Loaded: image grid; quarantined images carry a badge

## Verification
- Test files: `services/api/tests/test_curation.py` (`test_list_datasets_summarizes_images`)
- Required cases: dataset summary counts (images only), name validation
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm build && pnpm test:api`
- Pass criteria: dataset listing test green; gallery renders real thumbnails against a seeded bucket

## Related Docs
- [Dataset Scan](dataset-scan.md)
- [File Browser](file-browser.md) (kept full-bucket explorer)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
