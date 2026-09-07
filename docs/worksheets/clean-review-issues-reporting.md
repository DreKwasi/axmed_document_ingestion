# Worksheet: clean-review-issues-reporting

> Purpose: durable handoff trace for one coherent change.

## Goal and acceptance checks

- Restore clean presentation of quotation review issues in `ProductTable.vue` without manufacturing policy review issue badges from low-confidence fields.
- Treat clean electronic formats without OCR (including EML and JSON with arbitrary source systems) as strong source evidence when leaf provenance is absent, preventing false `Low` classifications.
- Keep the `Confidence` column and `ProductDetailDrawer.vue` as the dedicated places for confidence badges and factor breakdowns.
- Pass all unit tests, linters, and Playwright E2E tests.

## Context and constraints

- The user reported an issue where line items (e.g., Novara EML `Azimax 250`) had dozens of red review issue badges stacked vertically under "Review issues" displaying raw confidence strings (`source evidence: unverified; association: unverified; independent validation: unavailable`).
- PRD 45.2 establishes that strong source evidence includes direct JSON, clean native PDF, and clear email text.
- PRD 45.5 explicitly specifies that reviewer UI translates confidence factors into plain-language summaries rather than repeating raw internal factor strings for every field.

## Plan

1. Update `backend/app/domain/confidence.py` so non-OCR sources without poor parser quality are recognized as strong source evidence when leaf provenance is absent.
2. Add backend regression test in `backend/tests/test_confidence.py` for email without leaf evidence.
3. Update `frontend/src/components/ProductTable.vue` so `reviewIssuesForLine` only returns actual quotation review issues matching `line_items[${index}]`.
4. Update `frontend/src/App.spec.ts` to test explicit review issue display.
5. Validate full targeted checks (`bin/agent-validate targeted`) and Playwright E2E.

## Work log and evidence

- Corrected `_classify_extracted_field` and `_source_evidence` in `backend/app/domain/confidence.py` to check `not signals.ocr_used and signals.parser_quality not in {"poor", "failed"}` rather than hardcoding only `pdf` and `json`.
- Added `test_clean_native_email_without_leaf_provenance_is_medium_not_a_review_failure` to `backend/tests/test_confidence.py` (passes with `Medium` confidence and empty `review_reasons`).
- Removed `policyIssues` and `sourcePolicyIssues` synthesis from `frontend/src/components/ProductTable.vue`, returning solely real `props.reviewIssues` for the line item.
- Formatted `backend/app/api/application.py`, `backend/app/workers/email_extraction.py`, and `backend/app/workers/pdf_extraction.py` to conform with Ruff linting and line-length limits.

## Tests, app run, and validation

- Backend pytest: 94 passed in 15.27s.
- Backend mypy: 34 source files cleanly verified.
- Backend Ruff: all checks passed.
- Frontend ESLint: 0 errors, 0 warnings.
- Frontend Vitest: 11 tests passed in `App.spec.ts`.
- Frontend Build: `vue-tsc` and `vite build` completed successfully.
- Playwright E2E: 2 passed in `frontend/e2e/`.
- `bin/agent-validate targeted`: all checks green.

## Review findings and resolutions

- The user noted: "For json and eml and all other file types we did not change how to report these issues."
- Confirmed that review issues should report genuine parser/commercial issues (`quotation.review_issues`), not synthesize raw confidence strings for low-confidence fields.

## Docs updated

- `docs/worksheets/clean-review-issues-reporting.md`
- `docs/system/test-catalog.md`

## Handoff / remaining work

- No remaining work for this issue.

## Final commit and tag

- Implemented in current working tree.
