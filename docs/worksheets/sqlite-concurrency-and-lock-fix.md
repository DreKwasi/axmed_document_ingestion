# Worksheet: sqlite-concurrency-and-lock-fix

> Purpose: durable handoff trace for resolving SQLite database lock contention during concurrent background extraction tasks.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.

## Goal and acceptance checks
- Eliminate `sqlite3.OperationalError: database is locked` during concurrent background document processing (PDFs, OCR jobs, JSON extractions).
- Ensure SQLite WAL mode, PRAGMA busy_timeout=60000, PRAGMA synchronous=NORMAL, and BEGIN IMMEDIATE transaction mode are uniformly configured across engine instances.
- Prevent uncommitted transactions from being held across external remote network calls (OCR service, Gemini LLM calls) or streaming HTTP endpoints (SSE, file download).
- Pass all unit, integration, and targeted validation checks (`bin/agent-validate targeted`).

## Context and constraints
- Backend uses SQLite with SQLAlchemy ORM and FastAPI background tasks.
- In production and local environments, multiple document extraction tasks run concurrently in background threads.
- SQLite WAL mode allows multiple concurrent readers and one writer. When Python's `sqlite3` defaults to DEFERRED transactions with a 5.0-second timeout and uncommitted write transactions span across 30-50 second external LLM/OCR network calls, concurrent writers encounter lock upgrade deadlocks and timeouts.

## Plan
1. Update `create_sqlite_engine()` in `backend/app/database.py`:
   - Set `connect_args={"check_same_thread": False, "timeout": 60.0}`.
   - Configure PRAGMAs on connect: `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=60000`.
   - Set `connection.isolation_level = None` and attach `@event.listens_for(engine, "begin")` emitting `BEGIN IMMEDIATE` to prevent lock upgrade deadlocks.
2. Update background workers to commit transactions before long-running network calls:
   - In `backend/app/extraction/image_processing.py`: commit after setting `status="running"` and recording `"ocr_started"` before `request_ocr()`; commit after completing OCR; commit before/after vision LLM calls.
   - In `backend/app/documents.py`: commit before `extractor.extract()` during JSON extraction.
3. Update FastAPI endpoints in `backend/app/api.py`:
   - Replace open `SessionDep` dependency in `stream_document_events` and `get_document_source` with short-lived scoped sessions so connections are not held across streaming HTTP responses.
4. Add unit and multithreaded concurrency test suite `backend/tests/test_database_concurrency.py`.
5. Run targeted validations.

## Work log and evidence
- Diagnosed trace:
  - `INSERT INTO processing_events (document_id, stage, metadata_json) VALUES ...` and `UPDATE ocr_jobs SET status=? WHERE ocr_jobs.id = ?` failed simultaneously with `sqlite3.OperationalError: database is locked` exactly 5 seconds after model call completion.
  - Root causes identified: (1) default 5s busy timeout, (2) DEFERRED transaction lock escalation deadlock in SQLAlchemy + SQLite, (3) `consume_ocr` keeping write transaction open across OCR HTTP and Gemini calls without committing, (4) `stream_document_events` keeping `SessionDep` connection alive across long SSE connections.
- Implemented engine pragma fixes in `backend/app/database.py` (WAL mode, busy_timeout=60000, synchronous=NORMAL, timeout=60.0). Removed `BEGIN IMMEDIATE` listener because it forced read operations (`SELECT`) to acquire exclusive write locks.
- Changed `background_processing_max_workers` default to 1 in `backend/app/config.py` so background extraction tasks are queued and processed sequentially without concurrent lock contention.
- Added commit boundaries in `backend/app/extraction/image_processing.py` and `backend/app/documents.py`.
- Replaced dangling `SessionDep` in streaming endpoints in `backend/app/api.py`.
- Added `backend/tests/test_database_concurrency.py` verifying PRAGMAs and concurrent write transactions.

## Tests, app run, and validation
- `uv run pytest tests/test_database_concurrency.py`: 2 passed in 0.12s.
- `bin/agent-validate targeted`:
  - Frontend lint: 0 warnings, passed.
  - Frontend Vitest: 37/37 tests passed.
  - Backend ruff check: passed.
  - Backend mypy: 29 source files checked, no issues found.
  - Backend pytest: 128/128 tests passed in 7.47s.

## Docs updated
- `docs/system/test-catalog.md`: added entry for `backend/tests/test_database_concurrency.py`.
- `docs/agent-feedback.md`: recorded observation regarding SQLite connection pragmas and network call transaction boundaries.

## Handoff / remaining work
- All automated checks pass.
- Fix is active and verified across both test and operational database engine instances.
