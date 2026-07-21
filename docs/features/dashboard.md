<!-- last_verified: 2026-07-21 -->
# Feature: Dashboard

## Purpose
Give an at-a-glance view of dataset quality: how many datasets and images are tracked, how
many quality issues the latest scans found, and how many files have been quarantined.

## Used By
- UI: `/` page (dashboard home)
- API: `GET /curation/stats`, `GET /curation/stats/issues`, `GET /scans`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — 4 stat cards (Datasets, Images, Issues Found, Quarantined)
- `apps/web/src/components/dashboard/issues-chart.tsx` — bar chart of issues by type
- `apps/web/src/components/dashboard/recent-scans-table.tsx` — most recent runs
- `apps/web/src/lib/queries.ts` — `useCurationStats()`, `useIssueTypeCounts()`, `useScans()`
- `services/api/app/runtime/curation.py` — `GET /curation/stats*` handlers
- `services/api/app/service/curation_stats.py` — aggregation logic

## Canonical Files
- Aggregation logic: `services/api/app/service/curation_stats.py`
- Stat cards: `apps/web/src/components/dashboard/stats-cards.tsx`

## Inputs
- None (dashboard loads data automatically)

## Outputs
- `GET /curation/stats` → `CurationStats` (datasets, images, issues_found, quarantined)
- `GET /curation/stats/issues` → `IssueTypeCount[]` (per-type counts for the chart)
- `GET /scans` → `ScanSummary[]` for the recent-scans table

## Flow
- Page loads → three parallel API calls (stats, issue-type counts, recent scans)
- Stat cards show datasets, images, issues found, files quarantined
- Issues-by-type chart aggregates the **latest completed run per dataset** (so re-running a
  scan does not double-count)
- Recent scans table shows the newest runs with status badges

## Edge Cases
- API unavailable → inline error states with retry
- No datasets / no scans yet → empty states prompting a seed + first scan
- A dataset re-scanned multiple times → only its latest completed run counts toward totals

## UX States
- Loading: skeletons for cards, chart, table
- Empty: "No issues yet" / "No scans yet"
- Loaded: populated cards, chart, table

## Verification
- Test files: `services/api/tests/test_curation.py`
- Required cases: stats aggregation, latest-run-per-dataset dedup, empty state
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: all pytest tests green, no ruff violations

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)
- [Curation Runs](curation-runs.md)
