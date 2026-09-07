# Worksheet: backend-structure-simplification

> Purpose: simplify backend navigation and remove unused HTTP and batch-persistence surfaces.
> Scope: route consolidation, package relocation, dead-code removal, tests, and architecture documentation.
> Constraint: preserve all extraction and human-review behavior; do not commit or tag this work.

## Goal and acceptance checks

- One `POST /api/v1/documents` endpoint accepts one or many source files.
- Batch, evaluation, diagnostics, and separate review-queue HTTP routes are removed when unused by the product UI.
- The FastAPI application lives at `app/api.py`; there is no `app/api/` package.
- Extraction code is grouped under `app/extraction/`; obsolete `domain/` and `workers/` package names are removed.
- Database, models, configuration, logging, document operations, events, and evaluations have direct descriptive module names.
- Existing source upload, processing, review, event streaming, re-extraction, download, and deletion behavior remains covered.
- The running app and full validation pass.

## Context and constraints

- The worktree contains validated, uncommitted JSON extraction changes that must be preserved.
- Five earlier local commits exist; the user explicitly requested no further commits.
- `workers/` contains in-process extraction functions and provider adapters, not a worker runtime.
- The frontend uses batch creation only to upload multiple files; it does not use batch listing or retrieval.
- Evaluation and diagnostics HTTP clients have no product UI callers.

## Plan

1. Capture the current route/import graph and run the existing app as a baseline.
2. Add focused tests for a unified single/multiple document upload contract and removed routes.
3. Remove batch persistence and unused product API routes.
4. Flatten technical modules and group extraction modules under `app/extraction/`.
5. Update frontend callers/types and repository documentation.
6. Run targeted checks, the application flow, full validation, and staged review.

## Work log and evidence

- 2026-09-07: Baseline `GET /health` returned HTTP 200 from the existing API on port 8000.
- 2026-09-07: Import and caller inventory found active product usage for document CRUD/review/events/re-extraction, but no UI usage for batch reads, review queue, diagnostics, or evaluations.
- 2026-09-07: Research review had no external provider configured; isolated systems, security/domain, and quality passes are required.

## Tests, app run, and validation

- `bin/agent-validate full` passes: frontend lint, 12 component tests, production build, 2 Playwright journeys, Ruff, mypy, 90 backend tests, and 5 evaluation-runner tests.
- The running API returned HTTP 200 from `/health` and exposed only the retained document/review/event routes.
- The live database upgraded to Alembic `20260907_21`; the existing zero-product image is now `failed` with a safe reason, while completed human decisions are excluded from the backfill.
- Browser inspection confirmed the Home table shows the failed source as `EXTRACTION FAILED`, the Zenith product table shows only quoted price, and the detail drawer shows a normalized price with bounded precision.
- The existing Zenith JSON source was explicitly re-extracted; Oxytocin now persists and displays `solution for injection`.

## Review findings and resolutions

- Independent reviewer command was unavailable. Separate manual passes covered behavior/test strength, code structure, and security/performance/UX.
- Quality: added regression coverage for complete dosage phrases, zero-product failure, preserved non-reviewable facts, display precision, and migration safety.
- Code quality: removed the lossy dosage/presentation splitter and kept the zero-product terminal decision at the shared quotation persistence boundary.
- Security/UX: user-safe failure reasons remain on the original source; approved/rejected records are not rewritten; raw source data is not added to logs or the UI.
- Full validation initially exposed Playwright files sharing one temporary database concurrently; the suite now uses one worker because the configured E2E server is shared.
- `bin/agent-sweep` completed without additional warnings; the remaining working-tree changes pass `git diff --check`.

## Docs updated

- Product PRD, implementation plan, architecture, backend map, README files, test catalog, this worksheet, and agent feedback.

## Handoff / remaining work

- No required implementation work remains for this request.

## Final commit and tag

Not applicable: user explicitly requested no commits.
