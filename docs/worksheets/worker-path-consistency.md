# Worksheet: worker-path-consistency

> Purpose: durable handoff trace for the stranded OCR-job configuration fix.
> Status: in progress.
> Owner: backend delivery.

## Goal and acceptance checks

- API and Huey resolve operational SQLite/upload paths identically from any working directory.
- A queued OCR job is not silently skipped because a worker reads a different database.
- The known stranded OCR job is resubmitted after the configuration fix is live.

## Context and constraints

The API was running from `backend/` while Huey ran from the repository root. Both consumed relative `data/*` settings, splitting persistent state between `backend/data` and repository-root `data`. Existing unrelated worktree changes remain untouched.

## Plan

1. Add a regression test for relative operational-path resolution.
2. Anchor configured database, task-queue, and upload paths to the backend directory.
3. Restart the local processes and requeue the affected OCR job.
4. Run targeted and full validation.

## Work log and evidence

- 2026-09-07: Confirmed the API document/OCR record lives in `backend/data/app.db`; its Huey task was consumed by a root-working-directory worker using `data/app.db`, where the job did not exist.
- 2026-09-07: Anchored relative SQLite, task-queue, and upload paths to `backend/`; OCR task dispatch now passes the API's absolute upload directory to the worker.
- 2026-09-07: Safely copied the known source into the canonical upload directory after checksum verification, restarted local API/Huey, and requeued its OCR job. It completed and produced one reviewable product.

## Tests, app run, and validation

- `backend/tests/test_settings.py` failed before the path-resolution fix and passed after it.
- `backend/tests/test_image_parser.py` verifies that the OCR task runner uses the API-supplied upload directory.
- Focused Ruff and mypy checks passed.
- `bin/agent-validate targeted` passed, including 78 backend tests.
- `bin/agent-validate full` passed: frontend lint, 8 component tests, production build, 2 Playwright journeys, Ruff, mypy, 78 backend tests, and 5 evaluation tests.
- Local API and browser verification: `64fd85d7-8fa8-4388-9597-c91708afd20e` now reports OCR `completed`, source status `needs_review`, 45% extraction confidence, and one extracted product; Home renders it as `REVIEW`.

## Review findings and resolutions

- `bin/agent-review implementation` and `bin/agent-review wrap-up` found no independent provider configured. Focused code-quality, path-consistency, worker dispatch, and user-visible recovery checks were completed locally.

## Docs updated

- `backend/README.md`
- `docs/system/architecture.md`
- `docs/system/test-catalog.md`

## Handoff / remaining work

No product behavior is intentionally left outstanding; root-level legacy data remains untouched.

## Final commit and tag

Pending commit and `worksheet/worker-path-consistency` tag.
