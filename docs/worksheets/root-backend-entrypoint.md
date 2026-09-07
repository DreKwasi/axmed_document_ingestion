# Worksheet: root-backend-entrypoint

## Goal and acceptance checks

- Expose a backend-root FastAPI entry point runnable as `uvicorn main:app`.
- Make the separate API and Huey-worker responsibilities explicit.

## Context and constraints

- The API accepts and stores a batch synchronously, but PDF/email semantic extraction and OCR are queued to Huey.
- The user asked for a simpler local backend start command without moving HTTP composition logic out of `app.api.application`.

## Plan

- Add a thin backend-root `main.py` that imports the existing application factory.
- Point local command documentation and helper scripts at `main:app`.
- Add a smoke test for the entry point.

## Work log and evidence

- Added `backend/main.py`; it delegates to the existing application factory without relocating HTTP composition code.
- Updated local and E2E launch commands to use `main:app`.

## Tests, app run, and validation

- `env PYTHONPATH=backend uv run --project backend pytest backend/tests/test_entrypoint.py -q` — passed.
- Started `uv run uvicorn main:app` from `backend/` on port 8012; `/health` returned 200.
- `bin/agent-validate full` completed frontend lint/tests/build/E2E, Ruff, mypy, and backend tests.

## Review findings and resolutions

- The original repository-root entry point was not importable under the backend test/runtime path. The backend root is the appropriate executable root.
- No independent reviewer is configured; isolated systems and quality checks found no remaining issue.

## Docs updated

- Root README, backend README, test catalog, and feedback log.

## Handoff / remaining work

- Start the Huey worker separately when processing PDF, email, or image uploads; the API alone only queues those jobs.

## Final commit and tag

- Pending.
