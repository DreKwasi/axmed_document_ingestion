# Worksheet: upload-exception-logging

> Purpose: durable handoff trace for one coherent change.
> Created: 2026-09-08.

## Goal and acceptance checks

- Unexpected upload failures emit a full application traceback to stderr.
- Logs include safe request correlation and file metadata, but never file contents.
- Clients receive a handled JSON 500 response so configured CORS headers remain present.
- A focused regression test proves the behavior.

## Context and constraints

- Production cross-origin GET requests work, while a multipart POST reached Railway and returned a plain-text 500 with no useful application log.
- The production backend traceback is unavailable, so this change improves observability without guessing at the underlying ingestion defect.

## Plan

1. Reproduce the unlogged unexpected-exception path at the API boundary.
2. Add focused exception logging and a safe handled response.
3. Run targeted validation, exercise the running application, then run full validation and review.

## Work log and evidence

- Reproduced the unhandled upload exception with a focused API test; before the change, `RuntimeError` escaped the application and the test failed without a handled response.
- Added traceback logging with request ID, file count, extensions, and content types. Raw filenames and file contents are excluded.
- Added a safe JSON 500 response carrying the correlation ID in both the body and `X-Request-ID`.
- Reproduced the PDF-only path locally: the native PDF upload timed out after 60 seconds and returned 422. LiteParse's Python wrapper shells out to a Node CLI; when Railway lacks that CLI, `CLINotFoundError` is not one of the exceptions currently normalized by the PDF adapter and can surface as the observed 500.

## Tests, app run, and validation

- Red: focused pytest raised the forced ingestion exception through Starlette.
- Green: `UV_CACHE_DIR=/tmp/axmed-uv-cache uv run --project backend pytest -q backend/tests/test_document_uploads.py::test_unexpected_upload_failure_is_logged_and_returns_correlated_cors_response` — 1 passed.
- `UV_CACHE_DIR=/tmp/axmed-uv-cache uv run --project backend ruff check backend/app/api.py backend/tests/test_document_uploads.py` — passed.
- Application smoke via `TestClient(create_app())` and `GET /health` — returned `{"status": "ok", "service": "axmed-document-intelligence"}`.
- The focused native-PDF upload test reproduced a 60-second LiteParse timeout and returned 422. Full validation was not repeated because this known PDF runtime failure is the next deployment fix; the logging slice itself is covered by focused checks.

## Review findings and resolutions

- `bin/agent-review implementation` reported no configured independent provider. Isolated inspection found no raw filename/content logging; request IDs are length/character constrained before interpolation.

## Docs updated

- Updated `backend/README.md` and `docs/system/test-catalog.md` with the upload error contract and regression coverage.

## Handoff / remaining work

- Redeploy the backend, retry the failing file, then correlate the response reference with Railway application logs to diagnose the underlying ingestion exception.

## Final commit and tag
