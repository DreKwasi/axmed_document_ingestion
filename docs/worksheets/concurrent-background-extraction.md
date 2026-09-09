# Worksheet: concurrent-background-extraction

> Purpose: durable handoff trace for one coherent change.

## Goal and acceptance checks

Allow independent document extractions from one upload to start concurrently rather than serializing behind FastAPI `BackgroundTasks`.

## Context and constraints

- Parsed intake remains synchronous and deterministic.
- Each semantic/OCR extraction already opens its own SQLAlchemy session.
- Do not commit automatically. Browser tests are out of scope.

## Plan

1. Replace ordered FastAPI background-task scheduling with a bounded application-owned executor.
2. Keep worker lifecycle and failure records unchanged; add concurrent-submission visibility.
3. Prove two PDF jobs enter their worker bodies concurrently.

## Work log and evidence

- 2026-09-09: Confirmed Starlette `BackgroundTasks.__call__` awaits its task list in a `for` loop, so multiple files submitted in one request are serialized.
- 2026-09-09: Updated JSON result tests to explicitly wait for the independent worker's terminal document state rather than treating an asynchronous upload response as a completed extraction. JSON re-extraction schedules from its serialized queued response, avoiding stale in-memory status observations.

## Tests, app run, and validation

- Focused integration test: `uv run --project backend pytest backend/tests/test_document_uploads.py backend/tests/test_processing_events.py -q` passed (10 tests). It uses a two-party barrier in patched PDF workers; the request succeeds only when both job bodies enter concurrently.
- Ruff and mypy pass.
- `bin/agent-validate targeted` passes: frontend lint/tests, Ruff, mypy, and 122 backend tests. Browser tests remain intentionally excluded from this session.

## Review findings and resolutions

- The executor is intentionally bounded (`BACKGROUND_PROCESSING_MAX_WORKERS`, default 4) and waits for active jobs during graceful API shutdown. Each worker continues to create its own SQLAlchemy session.

## Docs updated

- `backend/README.md`, `docs/system/architecture.md`, `docs/system/test-catalog.md`, and `docs/agent-feedback.md` record the concurrency boundary and configuration.

## Handoff / remaining work

- This is process-local concurrency, not a durable distributed queue. A deployment restart waits for in-flight jobs during graceful shutdown; abrupt process loss still needs a future durable queue with recovery if that becomes a production requirement.
- Do not commit automatically; user instruction.

## Final commit and tag

Not created by user instruction.
