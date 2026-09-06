# Worksheet: di-08-batch-processing

> Purpose: durable handoff trace for independent batch processing and failure isolation.
> Scope: multi-document batch ingestion, derived aggregate progress, failure isolation, and batch API.
> Status: completed.
> Dependencies: Slices 1–5 completed, Slice 6 local contracts ready.
> Source requirements: PRD section 50 and Slice 8 in `docs/plans/implementation-plan.md`.
> Trust boundary: each child document processes independently; failures are isolated without blocking siblings.

## Goal and acceptance checks

- Persisted `BatchRecord` links child documents and computes derived aggregate status without counter drift.
- Multi-file batch intake API endpoint (`POST /api/v1/batches`) and batch query endpoint (`GET /api/v1/batches/{id}`).
- Failure isolation: an unparseable or corrupt file receives `status="failed"` and records an error reason, while valid sibling files continue processing and enter review.
- Frontend multi-upload tracks batch state and displays isolated failures cleanly without blocking siblings.

## Context and constraints

- SQLite WAL mode; child documents must retain their individual identities, lifecycle events, and review workflows.
- Batch progress must be derived from child document state rather than maintained via duplicate counters.
- No PII in batch error messages or logs.

## Plan

1. Create migration `20260906_10_batches.py` adding `batches` table and `batch_id` foreign key on `documents`.
2. Add `BatchRecord` model and update `DocumentRecord` in `backend/app/infrastructure/models.py`.
3. Add batch services (`create_batch`, `serialize_batch`) and update ingestion to accept `batch_id` in `backend/app/application/documents.py`.
4. Add batch endpoints (`POST /api/v1/batches`, `GET /api/v1/batches/{id}`) with failure isolation in `backend/app/api/application.py`.
5. Add unit and integration tests in `backend/tests/test_batch_processing.py`.
6. Update frontend API, types, and Vue UI in `frontend/src/`.
7. Verify with `bin/agent-validate targeted` and Playwright E2E.

## Work log and evidence

- 2026-09-06: Added migration `20260906_10_batches.py` creating the `batches` table and adding `batch_id` and `failure_reason` to `documents`.
- 2026-09-06: Updated `backend/app/infrastructure/models.py` with `BatchRecord` and `DocumentRecord` relationships.
- 2026-09-06: Added `create_batch`, `serialize_batch`, and `ingest_failed_document` in `backend/app/application/documents.py`. Aggregates are computed on the fly from child documents.
- 2026-09-06: Added `POST /api/v1/batches`, `GET /api/v1/batches`, and `GET /api/v1/batches/{id}` in `backend/app/api/application.py`. Invalid files in a batch produce isolated `failed` document records with specific error messages while sibling files process normally.
- 2026-09-06: Added `backend/tests/test_batch_processing.py` covering multi-file upload, aggregate metrics, and failure isolation.
- 2026-09-06: Updated `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/App.vue`, `frontend/src/styles.css`, and `frontend/src/App.spec.ts` with batch indicator and isolated failure rendering.
- 2026-09-06: Added Playwright E2E test `frontend/e2e/batch.spec.ts`.

## Tests, app run, and validation

- `pytest backend/tests/test_batch_processing.py -v`: 2 passed in 0.13s.
- `npm --prefix frontend test`: 7 tests passed in 0.6s.
- `npm --prefix frontend run test:e2e`: 2 E2E tests passed in 1.7s.
- `bin/agent-validate full`: All 47 Pytest tests, 7 Vitest tests, 2 Playwright tests, and linters passed.

## Review findings and resolutions

- Quality persona check: Verified that a corrupt JSON file in a batch does not raise a 422 HTTP exception aborting the batch; instead, it is captured as an isolated failed document record with its specific parsing error, while valid siblings continue to review.
- System persona check: Verified that batch progress is derived from database queries over child documents rather than relying on stateful increment counters that could drift on crash.

## Docs updated

- `docs/system/architecture.md`
- `docs/system/test-catalog.md`

## Handoff / remaining work

- Slice 8 complete. Ready for Slice 9 delivery hardening wrap-up.
