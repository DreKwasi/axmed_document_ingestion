# Worksheet: api-background-processing

> Purpose: durable handoff trace for one coherent change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.

## Goal and acceptance checks

Replace Huey-driven document and correction processing with API-owned Python background tasks. Uploads and batches must return promptly, each source must retain its independent processing state and SSE timeline, and no Huey process or SQLite task queue may be required.

## Context and constraints

Observed 2026-09-07: Huey consumers could leave Gemini invocations and source rows permanently `running`; claimed jobs were absent from the durable queue. User requested removal of Huey for now. Existing unrelated commercial-rules changes are preserved.

## Plan

1. Replace enqueue calls with API background-task dispatch.
2. Remove Huey runtime/configuration/dependency and related documentation.
3. Add focused API tests for independent asynchronous dispatch and failure isolation.
4. Update the single PRD, architecture, implementation plan, test catalog, README, and developer commands.

## Work log and evidence

- 2026-09-07: `bin/agent-review research` found no independent provider; isolated systems, security, and quality review will be recorded at wrap-up.
- 2026-09-07: removed Huey dispatch, the worker task module, its SQLite queue configuration, and its locked dependency. Reused the synchronous `consume_*` functions as API-owned task bodies rather than duplicating extraction behavior.
- 2026-09-07: upload, batch, and correction-review endpoints now receive FastAPI's `BackgroundTasks` dependency and call `.add_task()` with stable IDs. Each task opens its own database session and writes a failure event if it raises.
- 2026-09-07: added safe terminal lifecycle records for scheduling, task start, completion duration, and failure type. Records use short document/job IDs only; source text, credential values, and provider response text are never logged.
- 2026-09-07: confirmed with an isolated Uvicorn API probe that a PDF upload returned while its native background task advanced the extraction from `queued` to `awaiting_model_configuration` without a Gemini key.
- 2026-09-07: made `GEMINI_API_KEY` the only accepted Gemini credential name; removed `GOOGLE_API_KEY` and `AXMED_GEMINI_API_KEY` fallback behavior. Added a 60-second Gemini request timeout and disabled SDK retry amplification.

## Tests, app run, and validation

- Focused: `cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest tests/test_batch_processing.py tests/test_settings.py tests/test_langchain_gemini.py -q`.
- Full: `bin/agent-validate full` passed — frontend lint/tests/build/E2E, Ruff, mypy, 95 backend tests, and stored evaluations.

## Review findings and resolutions

- FastAPI's official pattern is suitable for the current local single-process operation: inject `BackgroundTasks` into the path operation and add ordinary functions after persistence. It remains deliberately non-durable across an API restart; a durable queue can be reconsidered after the extraction path is stable.
- No independent review provider was configured for `bin/agent-review`; the repository's isolated review stages were run instead.
- Wrap-up review: checked API route signatures, task/session ownership, task-failure events, credential names, docs, and validation evidence. No unresolved implementation defect found; the only accepted operational trade-off is same-process, non-durable task execution.

## Docs updated

- Single PRD, implementation plan, architecture, test catalog, root/backend/app READMEs, and local dev/e2e scripts document the API-owned background processing model and canonical environment names.

## Handoff / remaining work

- The reloader at `http://127.0.0.1:8000` will pick up the change. On the next PDF upload, verify the terminal shows the scheduling/start/completion or failure-type records. No code work remains.

## Final commit and tag
