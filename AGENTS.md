<!-- last_verified: 2026-06-25 -->
# AGENTS.md

This is the authoritative control surface for all coding agents. Read this first.

## 1. Repository Map

```
apps/web/          Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
services/api/      FastAPI backend (layered: types/config/repo/service/runtime)
packages/shared/   Shared TypeScript types
docs/              System of record (features, workflows, security, reliability)
docs/exec-plans/   Execution plans and tech debt tracker
infra/railway/     Deployment config
```

## 2. Extending This App

This app is built on the vibe-coding-starter-kit. The curation surface (Scans, Datasets) is
layered **on top of** the reusable B2 scaffolding — none of the starter surface was stripped.

**The curation surface (this app's primary feature)**
- **Scans** — `/scans`, `/scans/new`, `/scans/[runId]`, `apps/web/src/components/scans/`. A
  *Curation Run* is one fastdup scan over one dataset. Create → background run → report → clean.
- **Datasets** — `/datasets`, `/datasets/[name]`, `apps/web/src/components/datasets/`. The
  app-scoped image gallery (thumbnails via presigned URLs) with quality flags.
- Backend: `repo/scanner.py` (the ONLY fastdup import — mirrors the "SDKs in repo/" rule),
  `repo/b2_curation.py` (S3 helpers), `service/datasets.py` (key layout + gallery),
  `service/curation.py` (run lifecycle), `service/curation_stats.py` (dashboard),
  `service/report_artifacts.py` (report.csv/gallery.html), `runtime/{scans,datasets,curation}.py`,
  `types/curation.py`. Shared TS types in `packages/shared/src/types.ts`.

**Kept from the starter (do NOT strip, rename, or replace)**
- **UI kit / design system.** `apps/web/src/components/ui/` (shadcn primitives), the design
  tokens in `apps/web/src/app/globals.css`, and the `/design` page. Never edit generated
  `components/ui/` files directly — restyle through tokens in `globals.css`.
- **File browser.** `/files` route + `apps/web/src/components/files/`. Browses the **whole
  bucket** (not just this app's prefix) — kept as the reusable B2 surface, alongside the
  app-scoped Datasets gallery.
- **Upload.** `/upload` route + `apps/web/src/components/upload/` (generic B2 upload to
  `uploads/`; still uses `service/metadata.py`).
- **Settings** — `/settings` + `apps/web/src/components/settings/` (also the Form-UX exemplar
  the New-scan form is modeled on).

**Data-fetching rule** — every new aggregation flows through `runtime -> service -> repo` and
is exposed via TanStack Query hooks in `apps/web/src/lib/queries.ts`. No bare `useEffect + fetch`.

### Route / feature map

| Route | Feature | Backend endpoints |
|-------|---------|-------------------|
| `/` | Curation dashboard | `GET /curation/stats`, `GET /curation/stats/issues`, `GET /scans` |
| `/scans`, `/scans/[runId]` | Curation runs (read) | `GET /scans`, `GET /scans/{run_id}` |
| `/scans/new` | New scan (create) | `POST /scans` |
| (report actions) | Clean / delete a run | `POST /scans/{run_id}/clean`, `DELETE /scans/{run_id}` |
| `/datasets`, `/datasets/[name]` | Datasets explorer | `GET /datasets`, `GET /datasets/{name}` |
| `/upload` | Generic B2 upload (kept) | `POST /upload` |
| `/files` | Full-bucket browser (kept) | `GET /files`, `GET /files/{key}`, … |

## 3. Architectural Invariants

**Backend layering**: `types` -> `config` -> `repo` -> `service` -> `runtime`

- No backward imports across layers
- No `boto3` outside `repo/`
- No business logic in route handlers (`runtime/`)
- All external APIs wrapped in `repo/` adapters
- All request/response data validated at boundary (Pydantic models)
- No shared mutable state across layers

**Frontend**: shadcn/ui components in `src/components/ui/` are generated — never modify them.

**Data fetching**: every API call flows through TanStack Query hooks in `apps/web/src/lib/queries.ts`. No bare `useEffect + fetch` patterns. New endpoints touch three files: `runtime/<router>.py`, `lib/api-client.ts`, `lib/queries.ts`.

## 4. Quality Expectations

- **DRY** — do not duplicate logic, types, or constants. Extract shared code only when used in 2+ places.
- Structured JSON logging only — no `print()` statements
- No raw SDK calls outside `repo/` layer
- Files stay under 300 lines
- Tests added or updated for every behavior change
- Docs updated in same PR as code changes
- Lint clean before merge
- Prefer boring, composable libraries over clever abstractions
- No implicit type assumptions — use typed models

## 5. Mechanical Enforcement

| Rule | Enforced by |
|------|-------------|
| No backward imports | `tests/test_structure.py::test_no_backward_imports` |
| No boto3 outside repo/ | `tests/test_structure.py::test_boto3_only_in_repo` |
| File size < 300 lines | `tests/test_structure.py::test_file_size_limits` |
| All layers exist | `tests/test_structure.py::test_all_layers_exist` |
| No bare print() | `ruff` rule T20 |
| Import ordering | `ruff` rule I001 |
| Frontend strict equality | `eslint` rule eqeqeq |
| No unused vars | `eslint` + `ruff` rules |

## 6. Commands

```bash
# Run
pnpm dev               # start both frontend and backend
pnpm dev:web           # frontend only
pnpm dev:api           # backend only

# Test & Lint
pnpm lint              # frontend lint (eslint)
pnpm build             # frontend type check + build
pnpm test:web          # frontend unit tests (vitest)
pnpm lint:api          # backend lint (ruff)
pnpm test:api          # backend tests (pytest)
pnpm check:structure   # structural boundary tests
pnpm test:e2e          # Playwright e2e tests
```

CI (`.github/workflows/ci.yml`) runs these gates on every PR and push to `main`.

## 7. Agent Workflow

1. Read this file first.
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) before structural changes.
3. For non-trivial changes, create a plan in `docs/exec-plans/active/`.
4. Implement the smallest coherent change.
5. Run: `pnpm lint && pnpm test:web && pnpm lint:api && pnpm test:api && pnpm check:structure`
6. Update docs in the same PR (see §9).
7. Move completed plans to `docs/exec-plans/completed/`.
8. Only change files relevant to the task. No drive-by improvements.

## 8. Frontend Conventions

See [docs/dev-workflows.md](docs/dev-workflows.md) for full details.

## 9. Doc Update Mapping

| Change Type | Update Location |
|-------------|-----------------|
| Feature logic, inputs, outputs, tests | `docs/features/<feature>.md` |
| User journeys | `docs/app-workflows.md` |
| System layout, deployments | `ARCHITECTURE.md` |
| Dev or testing process | `docs/dev-workflows.md` |
| Setup or scope changes | `README.md` |
| Security changes | `docs/SECURITY.md` |
| Reliability changes | `docs/RELIABILITY.md` |
| Active work plans | `docs/exec-plans/active/` |
| Known tech debt | `docs/exec-plans/tech-debt-tracker.md` |

If documentation and implementation conflict, update docs in the same PR. Documentation rot destroys agent reliability.

## 10. Doc Map

| Topic | Location |
|-------|----------|
| System layout, data flows, boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Feature docs | [docs/features/](docs/features/) |
| User journeys | [docs/app-workflows.md](docs/app-workflows.md) |
| Engineering workflows and testing | [docs/dev-workflows.md](docs/dev-workflows.md) |
| Security principles | [docs/SECURITY.md](docs/SECURITY.md) |
| Reliability expectations | [docs/RELIABILITY.md](docs/RELIABILITY.md) |
| Execution plans | [docs/exec-plans/](docs/exec-plans/) |
| Tech debt | [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |

## 11. When Unsure

- Prefer boring, stable libraries
- Prefer small PRs over large changes
- Add tests with every change
- Never bypass lint rules without explicit instruction
- Ask before making destructive or irreversible changes
