<!-- last_verified: 2026-04-22 -->
# Security

Security principles and implementation for fastdup-dataset-cleaning.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/DELETE/OPTIONS`. `allow_credentials` is `False` (no cookie/session auth today); enable it only alongside real auth and a tightened origin allowlist.
- **API -> B2**: Authenticated via `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4. The S3 endpoint is derived from `B2_REGION` (no region hardcoded in source).
- **Client -> B2**: Presigned URLs — downloads force `Content-Disposition: attachment`; gallery/report thumbnails use short-lived inline presigned GETs (~15-min expiry).

## Safe Cleaning & Scoped Deletes

- **Cleaning never deletes.** Applying cleaning to a run **copies** flagged files to
  `datasets/<name>/quarantine/` via server-side `copy_object`; the originals under `raw/` are
  left in place, so cleaning is always reversible.
- **Deletes are prefix-scoped.** The only delete in the app, `DELETE /scans/{run_id}`, removes
  exactly one run's `datasets/<name>/quality-reports/<run-id>/` prefix. `repo.delete_prefix`
  refuses an empty prefix, so a bug can never wipe the dataset or bucket.
- **Path/name validation.** `run_id` (`^[A-Za-z0-9]{6,64}$`) and dataset `name`
  (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`) are validated before being used to build a B2 prefix,
  preventing traversal into other prefixes.

## Upload Validation

- Filename sanitization: path traversal, null bytes, unsafe chars stripped
- MIME/extension consistency check against allowlist
- Chunked streaming with size enforcement (100MB default)
- Content-type allowlist (images, PDFs, text, archives, audio/video). **SVG is excluded** — it can embed `<script>` that executes when served from a public bucket URL (stored XSS). Re-add only with server-side sanitization.
- **Magic-byte signature check**: for binary types, the leading bytes must match the declared content type, so a script payload can't masquerade as `image/png`. Text-like types (plain/CSV/JSON) have no signature and skip this check.
- Empty file rejection

## Rate Limiting

- Per-IP fixed-window limiter (`app/runtime/ratelimit.py`), configurable via `RATE_LIMIT_PER_MINUTE` (reads) and `RATE_LIMIT_WRITE_PER_MINUTE` (uploads/deletes/downloads). Guards against DoS and Backblaze transaction/egress cost amplification on the unauthenticated endpoints.
- In-process, per replica. Horizontal scaling needs a shared store (e.g. Redis) — see [RELIABILITY.md](RELIABILITY.md).

## File Key Validation

- Empty keys rejected
- Path traversal patterns rejected (`../`, `%2e%2e`, backslashes, null bytes)
- Optional prefix confinement: set `ALLOWED_KEY_PREFIX` (e.g. `uploads/`) to restrict key-addressed reads/deletes when the bucket is shared with other workloads. Empty by default — the by-key routes otherwise accept arbitrary folder and reserved-word keys by design.

## Download Safety

- Presigned URLs force `Content-Disposition: attachment`
- Prevents inline rendering of user-uploaded content (XSS mitigation)

## Response Hardening

- Baseline headers on every API response: `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`
- Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are on by default but can be disabled with `ENABLE_DOCS=false` to hide the API surface in production

## Secrets Management

- All secrets loaded via environment variables (pydantic-settings)
- Never committed to source control
- `.env.example` documents required variables without values

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never weaken validation without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
