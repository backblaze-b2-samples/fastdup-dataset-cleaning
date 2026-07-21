<!-- last_verified: 2026-07-21 -->
# Feature: Safe Cleaning (Quarantine, Never Delete)

## Purpose
Act on a completed scan by moving the flagged files out of the way — **safely**. Cleaning
copies flagged objects to a `quarantine/` prefix and records a manifest; it never deletes an
original, so cleaning is always reversible.

## Used By
- UI: `/scans/[runId]` → "Apply cleaning" button
- API: `POST /scans/{run_id}/clean`

## Core Functions
- `services/api/app/service/curation.py` — `clean_run()`, `_flagged_keys()`
- `services/api/app/repo/b2_curation.py` — `copy_object()` (server-side copy), `put_bytes()` (manifest)
- `apps/web/src/lib/queries.ts` — `useCleanScan()`

## Canonical Files
- Cleaning logic: `services/api/app/service/curation.py` (`clean_run`)

## Inputs
- run_id: str (must reference a `complete` run)

## Outputs
- `POST /scans/{run_id}/clean` → `CleanResult` (run_id, quarantined_count, manifest_key, already_cleaned)
- Side effects:
  - each flagged object copied to `datasets/<name>/quarantine/<basename>` via S3 `copy_object`
  - a cleaned manifest written to `datasets/<name>/manifests/cleaned-<run-id>.csv`
  - the run's `status.json` updated (`cleaned: true`, `quarantined_count`)

## Flow
- Validate the run is `complete` (else 409)
- If already cleaned → return `already_cleaned: true` (idempotent, no re-copy)
- Collect flagged keys = all duplicate/near-duplicate `flagged` + all outliers + all broken
- Server-side copy each to `quarantine/` (the **original in `raw/` is untouched**)
- Write the manifest; mark the run cleaned

## Edge Cases
- Run not `complete` → `409 RunStateError`
- Run with zero issues → the UI disables the button; a call would quarantine nothing
- Re-clicking clean → idempotent (no duplicate copies)
- **Deletes are always prefix-scoped.** The only delete in the app is `DELETE /scans/{run_id}`,
  scoped to that run's `quality-reports/<run-id>/` prefix and guard-railed against an empty
  prefix in `repo.delete_prefix`. Dataset images and quarantined files are never touched by it.

## UX States
- Button disabled when the run is not complete, has no issues, or is already cleaned
- Success toast reports how many files were quarantined and that originals are untouched

## Verification
- Test files: `services/api/tests/test_curation.py`
- Required cases: copy-not-delete (asserts `copy_object` per flagged key, quarantine prefix,
  originals in `raw/`), reject-incomplete, prefix-scoped delete guard
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: cleaning + delete-guard tests green

## Related Docs
- [Curation Runs](curation-runs.md)
- [docs/SECURITY.md](../SECURITY.md)
