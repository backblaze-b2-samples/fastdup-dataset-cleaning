<!-- last_verified: 2026-07-21 -->
# fastdup Dataset Cleaning

Clean large image training datasets **before** you train on them. This sample scans
images stored in **[Backblaze B2](https://www.backblaze.com/cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-fastdup-dataset-cleaning)**
with [**fastdup**](https://github.com/visual-layer/fastdup) (Apache-2.0, runs locally on
CPU), surfaces quality issues — exact duplicates, near-duplicates, outliers, and
broken/corrupt files — and safely quarantines the flagged files **without ever deleting
your originals**.

B2 is both the **dataset store** (`datasets/<name>/raw/`) and the **artifact store**
(`datasets/<name>/quality-reports/<run-id>/` and `datasets/<name>/quarantine/`) for the
whole curation loop. Everything runs on local open source — **B2 credentials only, no
second API key.**

## The curation workflow

```
1. Ingest   →  images land in B2 under datasets/<name>/raw/   (seed script, or your own pipeline)
2. Scan     →  fastdup fingerprints the images on CPU and flags quality issues
3. Report   →  a report.json / report.csv / gallery.html is written back to B2
4. Clean    →  flagged files are copied to datasets/<name>/quarantine/ (originals untouched)
```

## Features

- **[Dataset quality scan](docs/features/dataset-scan.md)** — fastdup finds exact
  duplicates, near-duplicates, outliers, and broken/corrupt files. Runs locally on CPU;
  no external API key; **$0 per run**.
- **[Curation runs & report artifacts](docs/features/curation-runs.md)** — every scan is a
  durable run whose status and full report are stored as artifacts in B2, so listings and
  detail survive restarts.
- **[Safe cleaning (quarantine, never delete)](docs/features/dataset-cleaning.md)** — apply
  cleaning to copy flagged files to a `quarantine/` prefix and write a cleaned manifest.
  Originals are never deleted.
- **[Datasets explorer](docs/features/datasets-explorer.md)** — a gallery of the actual
  images in each dataset (real thumbnails via presigned URLs) with quality flags.
- **[Curation dashboard](docs/features/dashboard.md)** — datasets, images, issues-by-type,
  and quarantined counts at a glance.
- **B2 as dataset + artifact store** — everything through the S3-compatible API (boto3),
  a custom user agent on the client, and the standardized `B2_*` env vars.

Plus the reusable B2 scaffolding kept from the starter kit: a generic drag-and-drop
**Upload**, a full-bucket **File browser**, a **Settings** page, and a **Design System**
reference.

## What it looks like

**Dashboard** — curation metrics and recent scans:

![Dashboard showing datasets, images, issues-by-type, and recent scans](docs/images/fastdup-dashboard.png)

**Scan report** — flagged images grouped by issue type, with a one-click clean:

![Scan report showing duplicate and outlier thumbnails](docs/images/fastdup-scan-report.png)

## Quick Start

You need: Node.js >= 20, pnpm >= 9, Python >= 3.11, and a free
**[Backblaze B2 account](https://www.backblaze.com/cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-fastdup-dataset-cleaning)**.

**1. Install dependencies**

```bash
pnpm install
```

**2. Set up the backend** (installs fastdup + boto3 into a venv)

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ../..
```

**3. Add your B2 credentials**

```bash
cp .env.example .env
```

Open `.env` and fill in the four required values from the
[Backblaze B2 dashboard](https://secure.backblaze.com/b2_buckets.htm?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-fastdup-dataset-cleaning):

- **keyID** → `B2_APPLICATION_KEY_ID`
- **applicationKey** → `B2_APPLICATION_KEY` *(only shown once — paste it now)*
- **Bucket Unique Name** → `B2_BUCKET_NAME`
- **Region** (the middle of the bucket's Endpoint, e.g. `us-west-004`) → `B2_REGION`

`B2_PUBLIC_URL_BASE` is optional (only used to build public links for public buckets — the
app works without it; image rendering falls back to short-lived presigned URLs). The app
key needs **Read and Write** permission.

**4. Seed the demo dataset** (generates ~20 synthetic images with a few real quality issues)

```bash
python scripts/seed_demo_dataset.py
```

This uploads to `datasets/demo/raw/` — several distinct images plus a handful of exact
duplicates, near-duplicates, and one broken file, so a scan has real issues to find. It is
idempotent (safe to re-run) and keeps everything under the `datasets/demo/` prefix.

**5. Run it**

```bash
pnpm dev
```

Frontend at `localhost:3000`, API at `localhost:8000`. Go to **Scans → New scan**, pick the
`demo` dataset, and start a scan. When it completes, open the report to see the flagged
images, then click **Apply cleaning** to quarantine them. Interactive API docs are at
`localhost:8000/docs`.

`pnpm dev` runs `pnpm doctor` first — a preflight check for the common setup gotchas (wrong
Node/Python version, missing venv, missing or placeholder `.env`, ports in use).

## How B2 is used

Everything goes through the **S3-compatible API** via boto3, contained in the `repo/` layer:

| Operation | S3 call | Used for |
|-----------|---------|----------|
| Write artifacts / seed images | `put_object` | report.json/.csv, gallery.html, status.json, quarantine manifest |
| List dataset images / discover datasets | `list_objects_v2` (+ `Delimiter`) | gallery, dataset list, run listing |
| Stage images for a scan | `get_object` / `download_file` | fastdup reads local files |
| Quarantine flagged files | `copy_object` | server-side copy; originals untouched |
| Thumbnails / report previews | `generate_presigned_url` | real `<img>` rendering |
| Health check | `head_bucket` | `/health` |

The single boto3 client sets `Config(user_agent_extra="b2ai-fastdup-dataset-cleaning")`, and
the endpoint is derived from `B2_REGION` (no region string is hardcoded).

> **Scaling note (honest):** for the demo, a scan streams the dataset's images to a local
> temp working dir via the S3 API, because fastdup computes visual fingerprints from local
> files. The temp dir is deleted after the run. At true million-image scale you would shard
> and stream in batches — see [docs/features/dataset-scan.md](docs/features/dataset-scan.md)
> and [docs/RELIABILITY.md](docs/RELIABILITY.md).

## Tech Stack

- TypeScript, Next.js 16, React 19, Tailwind v4, shadcn/ui, Recharts
- TanStack Query — caching, dedup, retry for every fetch
- Python 3.11+, FastAPI, boto3, Pydantic v2, Pillow
- **fastdup** — local, CPU-only image dataset analysis (no external API key)
- Backblaze B2 (S3-compatible object storage)
- pnpm workspaces (monorepo)

## Commands

| Command | What it does |
|---------|-------------|
| `pnpm dev` | Start frontend + backend |
| `pnpm dev:web` | Frontend only |
| `pnpm dev:api` | Backend only |
| `pnpm build` | Build frontend |
| `pnpm lint` | Lint frontend |
| `pnpm lint:api` | Lint backend (ruff) |
| `pnpm test:web` | Frontend unit tests (vitest) |
| `pnpm test:api` | Backend tests (pytest) |
| `pnpm check:structure` | Verify layering rules |
| `python scripts/seed_demo_dataset.py` | Seed the demo dataset into B2 |

## Documentation Map

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](AGENTS.md) | Agent table of contents — start here |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, layering, data flows |
| [docs/features/](docs/features/) | Feature docs (scan, runs, cleaning, datasets, dashboard, upload, browser, metadata) |
| [docs/app-workflows.md](docs/app-workflows.md) | User journeys |
| [docs/SECURITY.md](docs/SECURITY.md) | Security principles |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | Reliability expectations |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Claude Agent B2 Skill

Manage Backblaze B2 from your terminal using natural language (list/search, audits, stale or
large file detection, security checks, safe cleanup).

Repo: [https://github.com/backblaze-b2-samples/claude-skill-b2-cloud-storage](https://github.com/backblaze-b2-samples/claude-skill-b2-cloud-storage)
