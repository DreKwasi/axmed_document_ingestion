# Worksheet: json-extraction-without-schema-reuse

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.

## Goal and acceptance checks

Replace JSON schema mapping and reuse with per-document semantic extraction. Persist quotation-relevant source facts even when canonical normalization is unavailable; do not let normalization uncertainty affect extraction confidence or document success.

## Context and constraints

- Existing worktree changes are user-owned and must be preserved.
- JSON source paths validate source recovery but are not exposed in the current review UI.
- Unmapped canonical fields remain blank; a human reviews the extracted quotation, never a mapping plan.

## Plan

1. Replace mapping provider contracts with a JSON profile/extraction contract.
2. Add normalized extracted-source-fact persistence and a migration removing mapping reuse state.
3. Update ingestion, lifecycle events, API, frontend types/components, tests, and documentation.
4. Exercise JSON upload and explicit re-extraction, then run targeted and full validation.

## Work log and evidence

- 2026-09-07: Existing code confirmed that `ingest_json` fingerprints schemas, persists `schema_mappings`, and blocks on mapping confirmation. `field_evidence` and `quotation_field_values` both require canonical paths, so neither can preserve unmapped source facts.
- 2026-09-07: Replaced the mapping contract with recursive in-memory JSON profiling and a per-document semantic extractor. Facts now keep raw values, JSONPaths, methods, numeric source-recovery confidence, normalization status, and optional canonical destinations in `extracted_source_facts`.
- 2026-09-07: Added JSONPath/value validation with one corrective extraction attempt. Valid facts survive a partial result; an uncertain or unpopulated canonical destination is downgraded to `unmapped`, never treated as a confidence or review failure.
- 2026-09-07: Added migration `20260907_19` to clear only unreviewed mapping-derived JSON projections, move those sources to `pending_extraction`, remove mapping/review-learning persistence, and preserve completed human-review audit rows.
- 2026-09-07: Removed the mapping-confirmation endpoint/UI/types, retired the unused generic semantic-resolver fallback, and added explicit JSON re-extraction from the retained upload.

## Tests, app run, and validation

- Focused JSON/migration suite: `cd backend && uv run pytest tests/test_json_extraction.py tests/test_migrations.py -q` → 10 passed.
- Backend suite and lint: `cd backend && uv run ruff check app tests && uv run pytest -q` → 88 passed; one upstream Starlette deprecation warning.
- Frontend: `cd frontend && npm test -- --run && npm run build` → 12 tests passed; production build passed.
- Repository targeted gate: `bin/agent-validate targeted` → frontend lint/tests, backend Ruff/mypy/tests passed.
- Repository full gate: `bin/agent-validate full` → frontend lint/tests/build, 2 Playwright E2E journeys, backend Ruff/mypy, 88 backend tests, and 5 evaluation tests all passed. The recorded evaluation run has one executable JSON case passing and five explicitly not-run live PDF/email/OCR cases.
- Live visual check: isolated API at `:8001` and Vite UI at `:5174`; uploaded the Sanova JSON fixture, verified source table/detail/product drawer, correct data, canonical-only drawer, no mapping-confirmation control, and source-fact data absent from the UI as intended. Screenshots: `/tmp/axmed-json-table.png`, `/tmp/axmed-json-product-detail.png`.

## Review findings and resolutions

- `bin/agent-review implementation` and `bin/agent-review wrap-up` found no configured independent review provider. Isolated local review passes completed: quality verified nested/flat/mixed, unmapped, retry, failure, and re-extraction behavior; code quality added the populated-canonical-value guard; security verified safe extractor failure text and no raw diagnostic exposure; UX verified the unchanged canonical-only product drawer; the final evidence and documentation were reconciled with the implementation.

## Docs updated

- Updated the single repository PRD, implementation plan, architecture, test catalog, backend/frontend READMEs, evaluation asset README, and this worksheet.

## Handoff / remaining work

- Ready for commit. Existing unrelated worktree changes remain intentionally unstaged.

## Final commit and tag

Pending.
