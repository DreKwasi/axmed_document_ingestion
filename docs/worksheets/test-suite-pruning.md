# Worksheet: test-suite-pruning

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

Reduce the automated-suite surface by removing redundant or stale tests while retaining meaningful behavioral coverage for supported flows. The focused and full validation commands must pass, and the test catalog must describe the remaining suite accurately.

## Context and constraints

The initial suite had 169 test declarations across backend unit/integration tests and frontend component/E2E tests (6,031 lines). The user clarified that this slice must focus on backend tests. Existing uncommitted user changes are out of scope and must be preserved.

## Plan

Inventory overlapping test cases, retain one high-signal behavioral test per seam, remove superseded low-value variants, update the catalog, then validate the application and suites.

## Work log and evidence

- 2026-09-09: Read `AGENTS.md`, workflow, coding conventions, testing strategy, test catalog, task queue, and review protocol. Research review reported no independent provider is configured; isolated persona passes will be recorded below.
- 2026-09-09: Restored an initial frontend-only pruning attempt after the user narrowed scope to backend tests.
- 2026-09-09: Removed duplicated backend cases: the processing-events PII test (owned by the PII audit suite), the email/PDF worker-provider integrations (owned by their parser-worker suites), a weaker zero-product JSON failure variant, and a weaker single-low-score OCR confidence variant. Retained the shared provider seam, parser-worker integration, OCR dual-path integration, and stronger boundary variants.

## Tests, app run, and validation

- Live app check: `curl http://127.0.0.1:8000/health` returned `{"status":"ok","service":"axmed-document-intelligence"}`; both frontend ports 5173 and 5174 returned HTTP 200. A pre-existing API process occupied port 8000.
- Focused: `uv run --project backend ruff check backend/tests/test_langchain_gemini.py backend/tests/test_json_extraction.py backend/tests/test_confidence.py backend/tests/test_processing_events.py` — passed.
- Focused: `uv run --project backend pytest backend/tests/test_langchain_gemini.py backend/tests/test_json_extraction.py backend/tests/test_confidence.py backend/tests/test_processing_events.py -q` — 33 passed (one third-party AnyIO deprecation warning).
- Full backend: `uv run --project backend pytest backend/tests -q` — 124 passed (one third-party AnyIO deprecation warning).
- Frontend unit checks run by `bin/agent-validate targeted` and `full` passed: 39 tests and ESLint.
- Full validation limitation: `bin/agent-validate targeted` stops at a pre-existing Ruff import-order error in `backend/app/extraction/image_processing.py`. `bin/agent-validate full` reaches a pre-existing TypeScript fixture error in `frontend/src/components/SourceTable.spec.ts` before backend checks. Neither file is part of this test-pruning change.
- Frontend build direct check was blocked by the same `SourceTable.spec.ts` required `ImageExtractionAttempt.result` fixture error. Playwright E2E was blocked because the local Chromium executable is not installed.

## Review findings and resolutions

- Research and plan reviews: no independent provider is configured. Systems review found the worker-provider tests duplicated parser-worker lifecycle coverage; quality review retained the shared semantic seam and source-specific OCR integration; security review retained the dedicated PII audit as the single owner of redaction behavior.
- Implementation review: no independent provider is configured. Isolated quality/code-quality/security passes found the removed tests had direct stronger owners and the change did not weaken source-specific parser, OCR, provider, PII, JSON validation, or confidence-boundary coverage.

## Docs updated

- `docs/system/test-catalog.md` now identifies the remaining owner suites for provider, parser-worker, and PII behavior.

## Handoff / remaining work

- The backend test suite now has 121 declarations in 3,438 lines, down from 126 declarations in 3,611 lines before this backend-focused cleanup. Fix the unrelated Ruff and frontend fixture failures, and install Playwright Chromium, before relying on repository-wide full validation.

## Final commit and tag
