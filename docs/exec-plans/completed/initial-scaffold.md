# Build plan — `fastdup-dataset-cleaning`

Source of truth (starter kit): `.claude/scratch/vcsk-dbcd3c7d-3999-4625-a416-d4430ec65e6d/`.
Build target: `./fastdup-dataset-cleaning`. Standards: `../CLAUDE.md`.

## 1. Purpose

`fastdup-dataset-cleaning` is a B2 sample for **ML engineers and data-curation
teams** who need to clean large image training datasets before training. It uses
**fastdup** (https://github.com/visual-layer/fastdup, Apache-2.0, runs locally on
CPU) to scan images stored in Backblaze B2, surface quality issues — exact
duplicates, near-duplicates, outliers, and broken/corrupt files — and then safely
quarantine the flagged files (copy to a `quarantine/` prefix, write a cleaned
manifest) **without ever deleting originals**. B2 is both the **dataset store**
(`datasets/<name>/raw/`) and the **artifact store** (`datasets/<name>/quality-reports/<run-id>/`
and `datasets/<name>/quarantine/`) for the whole curation loop. Everything runs on
local OSS — **B2 credentials only, no second API key**.

## 2. Architecture delta from vibe-coding-starter-kit

The starter kit is the ceiling. Keep the full-stack scaffold, strip nothing that
is part of the starter contract, adapt the Dashboard, and add the curation surface.

### KEEP (as-is — starter contract, do not strip/rename)
- **UI kit** `apps/web/src/components/ui/*` (all shadcn primitives) + design tokens
  in `globals.css` + `/design` page and its components. Never edit generated `ui/` files.
- **Bucket Explorer** — `/files` route, `app/files/`, `components/files/*`. **NON-NEGOTIABLE KEEP**:
  full-bucket browse stays exactly as-is (browses the whole bucket, not just this app's prefix).
- **Upload** — `/upload` route, `app/upload/`, `components/upload/*`. Sidebar entry stays.
  (Generic B2 upload to `uploads/`; kept as the reusable B2 surface. Dataset ingestion for the
  demo is via the seed script, §7.)
- **Settings** — `/settings` + `components/settings/*` (also the form-UX exemplar). Keep.
- Backend layered architecture (`types → config → repo → service → runtime`), the
  structural tests, JSON logging, `/health`, `/metrics`, rate limiting, CORS ordering,
  request-id/timing middleware, TanStack Query data layer, error/empty-state patterns,
  `scripts/doctor.mjs` + `dev.sh` + `pick-port.mjs`, CI workflow, `infra/railway`.
- Metadata extraction (`service/metadata.py`) — still used by Upload; keep.

### TRIM (remove from starter)
- **Nothing structural.** This sample is a superset of the starter's B2 surface.
- Dashboard *content* (default stats/chart/table) is replaced, not deleted — see ADAPT.
- Starter-kit copy/branding in README/AGENTS/ARCHITECTURE/docs is rewritten (see §5), not
  deleted wholesale.

### ADAPT
- **Dashboard** (`/` + `components/dashboard/*`): replace file-centric metrics with
  curation metrics (see §4 dashboard). New aggregations flow through
  `runtime → service → repo` and are exposed via TanStack Query hooks in `lib/queries.ts`
  (no bare `useEffect + fetch`). Update `docs/features/dashboard.md`.
- **Env vars → Standard #3** (see §3 + rename table §6): rename `B2_KEY_ID → B2_APPLICATION_KEY_ID`,
  introduce `B2_REGION` (build the S3 endpoint from it), `B2_PUBLIC_URL → B2_PUBLIC_URL_BASE`.
  This touches `config/settings.py`, `main.py` (REQUIRED/placeholder lists), `repo/b2_client.py`
  (endpoint construction + public-url), `.env.example`, `scripts/doctor.mjs`, README, docs.

### ADD (new for `fastdup-dataset-cleaning`)
- **Curation Run** primary entity (§4) — the fastdup scan + its report.
  - Backend: `repo/scanner.py` (fastdup adapter — contains the fastdup import, mirrors the
    "contain external SDKs in repo/" invariant), `repo/b2_client.py` new helpers
    (`download_prefix_to_dir`, `copy_object`, `list_prefixes`, `put_bytes`, `delete_prefix`),
    `service/curation.py` (orchestration + background run manager), `runtime/scans.py`,
    `runtime/datasets.py`, new types in `types/curation.py`.
  - Frontend routes: `/scans` (list + New-scan), `/scans/[runId]` (detail/report),
    `/scans/new` create form, `/datasets` (scoped asset explorer), `/datasets/[name]`.
  - Shared types added to `packages/shared/src/types.ts`.
- **Datasets Explorer** (`/datasets`) — **NON-NEGOTIABLE ADD**: the sample-specific asset
  explorer scoped to this app's own folder (`datasets/`). Lists datasets, and per dataset shows
  a **gallery of the actual images** (thumbnails via presigned preview URLs) with quality flags
  (duplicate / broken / quarantined). This is the "Library" analog required alongside the kept
  full-bucket explorer.
- Sidebar: add **Scans** and **Datasets** entries; keep Dashboard, Upload, Files, Settings,
  Design System.
- `scripts/seed_demo_dataset.py` — generates a small synthetic demo dataset at runtime (§7).

> **Bucket-explorer tension note:** none. The bucket explorer (`/files`) is kept in full; the
> Datasets explorer is added alongside it as the scoped view. No conflict.

## 3. B2 surface (S3-compatible only — Standard #1)

All operations via the S3 API through boto3, contained in `repo/`. **No b2-native API.**
- `put_object` — write report artifacts (`report.json`, `report.csv`, `gallery.html`,
  `status.json`), cleaned manifest, seed images.
- `list_objects_v2` (paginated) — list dataset images, list runs (via `status.json` keys),
  discover dataset prefixes.
- `get_object` — download dataset images to a local temp dir for fastdup; read report during clean.
- `copy_object` — quarantine flagged files (server-side copy to `quarantine/`; originals untouched).
- `head_object` — metadata.
- `generate_presigned_url` — image thumbnails/preview in the gallery + report + report download.
- `head_bucket` — `/health` connectivity (existing).

Custom user agent (Standard #2): set on the single boto3 client via
`Config(user_agent_extra="b2ai-fastdup-dataset-cleaning")`.

**Documented deviation (honest):** the use case says "without downloading the full corpus".
For the demo, the scan **streams the dataset's images to a local temp working dir via the S3
API** (boto3 `get_object`), because fastdup computes visual fingerprints from local files; the
temp dir is deleted after the run. At true million-scale you would shard/stream in batches — call
this out as a scaling note in `docs/features/dataset-scan.md` + `RELIABILITY.md`. This keeps the
code path identical and honest without pretending fastdup reads bytes it doesn't.

## 4. Key features + Primary-entity lifecycle

**External API provider:** NONE. fastdup is local OSS. **No Genblaze** (description does not
name a "Suggested stack"/Genblaze; it explicitly says "no second API key, B2 credentials only").

**Feature: Dataset quality scan (fastdup)** — `deployment: local`.
- Provider/model: fastdup (local, CPU). No external key. Cost per demo run: **$0**.
- CPU-default / GPU-autodetect rule: fastdup's feature extraction is **CPU-only** (ONNX CPU
  runtime); there is no GPU path to autodetect, so it defaults to and stays on CPU. Record this
  explicitly (satisfies the local-deployment hard rule — nothing to autodetect, never
  hard-requires a GPU).
- **macOS arm64 caveat (for the verify step, not the build):** fastdup's native wheel can be
  flaky on Apple Silicon. The build writes it to run natively on CPU; if the verify step finds the
  native wheel hangs/fails to import, it should containerize in a native `linux/arm64` python
  image (same precedent as paddleocr/deoldify). Build does NOT containerize.

Features (seed README feature list + `docs/features/<feature>.md`):
1. **Dataset quality scan** — fastdup finds exact duplicates, near-duplicates, outliers,
   broken/corrupt files. `deployment: local`, CPU, $0. → `docs/features/dataset-scan.md`
2. **Curation runs & report artifacts** — every scan writes structured artifacts
   (`report.json`/`.csv` + `gallery.html`) to B2 under `datasets/<name>/quality-reports/<run-id>/`.
   → `docs/features/curation-runs.md`
3. **Safe cleaning (quarantine, never delete)** — copy flagged files to
   `datasets/<name>/quarantine/`, write a cleaned manifest; originals never deleted.
   → `docs/features/dataset-cleaning.md`
4. **Datasets explorer** — scoped gallery of dataset images with quality flags.
   → `docs/features/datasets-explorer.md`
5. **Curation dashboard** — issues-by-type chart, quarantined counts, recent runs.
   → rewrite `docs/features/dashboard.md`
6. **B2 as dataset + artifact store** — S3 API, custom UA, standard `B2_*` vars (cross-cutting;
   covered in README + ARCHITECTURE).

### Primary entity: **Curation Run** (one fastdup scan over one dataset)

Lifecycle verbs (DEFAULT = all exposed in the UI; Phase 2 builds them):
- **create** ✅ BUILD — `/scans/new` "New scan" form → `POST /scans` starts a background run.
- **read** ✅ BUILD — `/scans` list (from `status.json` artifacts) + `/scans/[runId]` detail
  (report view with per-issue-type sections, image thumbnails, gallery).
- **run** ✅ BUILD — the scan execution IS the create action (background thread; status
  `running → complete/failed`, frontend polls). PLUS the **"Apply cleaning"** action on a completed
  run (`POST /scans/{run_id}/clean`) — a second run-style verb, built.
- **delete** ✅ BUILD — `/scans/[runId]` delete button → `DELETE /scans/{run_id}` removes only
  that run's artifacts (scoped to `datasets/<name>/quality-reports/<run-id>/` — prefix-guarded
  in the service; safe per CLAUDE.local.md).
- **edit** ❌ OMITTED (record in `omitted_ui_verbs`). **UX justification:** a curation run is an
  immutable record of a scan at a point in time — the report reflects the dataset state when the
  scan ran and has no user-editable field. To re-curate with different settings the user starts a
  new run. An edit form would imply mutable results that don't exist.

### Form UX conventions — "New scan" create form
- **(a) Finite-value fields use selectors (not free text):**
  - `dataset` → **Select**, options from `GET /datasets` (finite set discovered in the bucket).
  - `sensitivity` → **Select** preset: `Strict (0.90)` / `Balanced (0.85)` / `Loose (0.80)`
    (maps to fastdup near-duplicate + ccthreshold). Never a raw float text box.
  - `issue_types` → **Checkbox** group: Duplicates, Near-duplicates, Outliers, Broken files
    (finite set; default all checked).
- Free-text field allowed: optional `label` (run name) — genuinely free-form.
- **(b) CREATE-form safe defaults as guidance (placeholder / `FormDescription`, never an
  autofill button):** dataset defaults to `demo` (FormDescription: "The seeded demo dataset is a
  good first run"), sensitivity defaults to **Balanced** (FormDescription explains the tradeoff),
  all issue types on. Model on `components/settings/settings-form.tsx` (Select + RadioGroup +
  FormDescription exemplar).
- No edit form (edit omitted) → the default-hint rule applies only to this create form; selector
  rule has no edit form to also cover.

### Backend endpoints (each new endpoint touches `runtime/*.py`, `lib/api-client.ts`, `lib/queries.ts`)
- `GET  /datasets` → list datasets under `datasets/` (name, image_count, size_human).
- `GET  /datasets/{name}` → images in `datasets/{name}/raw/` + quarantine flags (backs the gallery).
- `POST /scans` → start a run {dataset, sensitivity, issue_types, label?} → {run_id, status:"running"}.
- `GET  /scans` → list runs (parse each `status.json`).
- `GET  /scans/{run_id}` → status + parsed report when complete.
- `POST /scans/{run_id}/clean` → quarantine flagged files + write cleaned manifest.
- `DELETE /scans/{run_id}` → delete that run's artifacts (prefix-scoped).
- Dashboard: `GET /curation/stats` (datasets, images, issues-found, quarantined) +
  `GET /curation/stats/issues` (issue-type counts for the chart) + recent runs via `GET /scans`.

**Run/state model:** in-process background thread per run (documented single-replica caveat like
the existing rate limiter/counter). Run state lives in B2 as `status.json` (`running` →
`complete`/`failed`) so listing/detail are just artifact reads and state survives restarts —
this is also the artifact-store story. Media in the gallery/detail must **actually render** (real
`<img>` from presigned URLs) — the verify step requires media to paint, so wire real thumbnails,
not placeholders.

## 5. Doc transforms
- **README.md** — full rewrite for the sample: purpose, the 4-step curation workflow (ingest →
  scan → report → clean), Quick Start (renamed `B2_*` vars, `pip install` incl. fastdup, run seed
  script, walkthrough), feature list (§4), tech stack (+ fastdup), commands table, UTM content tag
  → `b2ai-fastdup-dataset-cleaning`. Reference screenshots at `docs/images/fastdup-*.png`
  (files created later by the screenshot step — do NOT create binaries now).
- **AGENTS.md** — keep all architectural invariants + mechanical-enforcement table; update repo
  name refs; rewrite §2 "Building on this starter kit" → "Extending this app" describing the
  curation surface (Scans, Datasets) and that Files/Upload/UI-kit stay; add Scans/Datasets to the
  route/feature map.
- **ARCHITECTURE.md** — add scan (background run) + clean data flows; note temp-dir download +
  B2 artifact state.
- **docs/features/**: rewrite `dashboard.md` (curation metrics); keep `file-upload.md`,
  `file-browser.md`, `metadata-extraction.md`; ADD `dataset-scan.md`, `curation-runs.md`,
  `dataset-cleaning.md`, `datasets-explorer.md` (use `_template.md`).
- **docs/app-workflows.md** — rewrite journeys around the curation loop.
- **docs/SECURITY.md** — add: cleaning quarantines (copies), never deletes; delete is
  prefix-scoped to a single run.
- **docs/RELIABILITY.md** — add: in-process background run caveat (single replica); temp-dir
  cleanup; million-scale sharding note.
- **docs/design-system.md**, `_template.md` — keep.
- Move this plan to `docs/exec-plans/completed/initial-scaffold.md` on PASS (Phase 5).

## 6. Rename table (`vibe-coding-starter-kit` → `fastdup-dataset-cleaning`)

| Kind | From | To |
|------|------|----|
| kebab slug | `vibe-coding-starter-kit` | `fastdup-dataset-cleaning` |
| root pkg name | `vibe-coding-starter-kit` | `fastdup-dataset-cleaning` |
| npm workspace scope | `@vibe-coding-starter-kit/web` | `@fastdup-dataset-cleaning/web` |
| npm workspace scope | `@vibe-coding-starter-kit/shared` | `@fastdup-dataset-cleaning/shared` |
| import specifier | `@vibe-coding-starter-kit/shared` (in api-client, queries) | `@fastdup-dataset-cleaning/shared` |
| FastAPI title | `OSS Starter Kit API` | `fastdup Dataset Cleaning API` |
| `APP_NAME` | `OSS Starter Kit` | `fastdup Dataset Cleaning` |
| `APP_DESCRIPTION` | `File management dashboard powered by Backblaze B2` | `Find and clean duplicate, broken, and low-quality images in B2-hosted training datasets` |
| user_agent_extra / UTM content | `b2ai-oss-start` | `b2ai-fastdup-dataset-cleaning` |
| CI/image/workflow refs | any `vibe-coding-starter-kit` | `fastdup-dataset-cleaning` |

**Env-var rename (Standard #3 — audited by /b2-doctor):**

| From (starter) | To (standard) | Notes |
|----------------|---------------|-------|
| `B2_KEY_ID` | `B2_APPLICATION_KEY_ID` | rename everywhere |
| `B2_APPLICATION_KEY` | `B2_APPLICATION_KEY` | unchanged |
| `B2_BUCKET_NAME` | `B2_BUCKET_NAME` | unchanged |
| `B2_ENDPOINT` | `B2_REGION` | settings takes region, builds `https://s3.{region}.backblazeb2.com`; keep an optional `B2_ENDPOINT` override only if trivial, but `B2_REGION` is the documented canonical var |
| `B2_PUBLIC_URL` | `B2_PUBLIC_URL_BASE` | **OPTIONAL** — keep out of the REQUIRED boot gate (do not make the app BLOCK when it is unset) |

REQUIRED at boot: `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`, `B2_REGION`.
`B2_PUBLIC_URL_BASE` stays optional. Update `main.py` REQUIRED/PLACEHOLDER lists, `settings.py`,
`b2_client.py` (endpoint from region + `_public_url` from `b2_public_url_base`), `.env.example`,
`scripts/doctor.mjs` (env checks), README.

## 7. Demo seed script — `scripts/seed_demo_dataset.py`
Generates a small synthetic dataset at runtime (Pillow) and uploads via the API's repo layer or a
standalone boto3 client using the same `B2_*` vars — **no committed binaries**:
- ~18–24 images to `datasets/demo/raw/`: several distinct solid/gradient patterns, **2–3 exact
  duplicates** (identical bytes under different names), **1–2 near-duplicates** (same image + light
  noise), and **1 broken file** (valid `.jpg` name, truncated/garbage bytes) so fastdup has real
  issues to find. Plus a `manifest.csv` (path,label) alongside.
- Idempotent (safe to re-run); documented in README ("Run the demo"). The verify/screenshot steps
  invoke it. Keep all demo data under the `datasets/demo/` prefix (shared-bucket safety).

## 8. Quality gates the builder must green (per AGENTS.md §5)
`pnpm lint`, `pnpm build`, `pnpm test:web`, `pnpm lint:api`, `pnpm test:api`, `pnpm check:structure`.
- Keep every backend file < 300 lines (split `service/curation.py` / `repo/scanner.py` if needed).
- boto3 only in `repo/`; fastdup import only in `repo/scanner.py`.
- Add tests for new behavior: scan lifecycle (mock scanner + mock B2), clean/quarantine
  (assert copy-not-delete + prefix scope), datasets listing, prefix-scoped delete guard, and keep
  the structural tests passing (new layers/files obey ordering).
- New endpoints each touch the three files (`runtime`, `api-client`, `queries`).
