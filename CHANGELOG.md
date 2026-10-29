# Changelog

## Unreleased — stage 2 continuation

- Added pinned upstream artifact acquisition with size, digest and tar-entry checks.
- Added API write result uncertainty handling and exact OpenAPI digest validation.
- Added managed Nginx panel include with idempotency and rollback on failure.
- Added certificate SAN/key/expiry checks and PostgreSQL restore into an empty dedicated database.
- Expanded unit tests and configured disposable PostgreSQL and Nginx checks in CI.
- Corrected `dry-run` to fail explicitly until a real planner exists.

## 0.1.0 — 2026-10-29

- Added modular read-only preflight and API inventory.
- Added SQLite online backup, verified new-file restore, and PostgreSQL custom-format backup.
- Added static 3.11.0 capability manifest and fail-closed mutation gates.
- Added unit tests and CI definition.
