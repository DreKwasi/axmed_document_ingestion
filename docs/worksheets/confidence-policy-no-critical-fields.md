# Worksheet: confidence-policy-no-critical-fields

> Purpose: remove the obsolete critical/key-field concept from confidence, review routing, API summaries, and UI.

## Goal and acceptance checks

- No fixed critical-field list or completeness gate remains in the confidence policy.
- Missing values alone do not create Low confidence or route human review.
- The source list shows Confidence and an explicitly named Review issues column.
- The source detail header contains confidence, not key-field coverage.
- Existing records are reassessed under the corrected policy.

## Context and constraints

- The user explicitly superseded the prior seven-field availability rule.
- Confidence remains per extracted source fact under canonical PRD V8.
- Explicit extraction failures, conflicts, ambiguity, validation failures, and weak evidence still route review.

## Plan

1. Write the absent-value routing regression first.
2. Remove required-field coverage from the domain result and API.
3. Replace key-field UI with source confidence and rename Issues to Review issues.
4. Update the canonical PRD/tests, reassess data, and validate the running app.

## Work log and evidence

- The new regression initially failed because absent quoted quantity still forced `needs_review`.
- Removed `REQUIRED_COMMERCIAL_FIELD_SUFFIXES` and coverage counters from `ReviewAssessment`.
- Removed `extraction_coverage` from document serialization and frontend types.
- Existing two quotations were reassessed; the image's review issue count fell from 19 to 13 because absence-only issues disappeared.
- API confirms neither document includes `extraction_coverage`.
- Browser confirms source columns are Source, Confidence, Review issues, Products, and Status; image detail says “Low confidence” with no key-field count.
- Removed the final obsolete “critical quotation fields” wording from the evaluation rubric and repository context.

## Tests, app run, and validation

- Focused backend: 26 passed.
- Backend mypy: passed from the configured backend project.
- Frontend Vitest: 10 passed.
- Frontend production build: passed.
- `bin/agent-validate full`: passed — frontend lint/build, 10 component tests, 2 E2E tests, 89 backend tests, mypy, Ruff, and 5 evaluation tests.

## Review findings and resolutions

- No independent provider was configured. Isolated behavior, code-quality, and UX/spec passes found and corrected one stale PDF expectation and one stale evaluation-rubric label; no unresolved findings remain.

## Docs updated

- Canonical PRD and test catalog.

## Handoff / remaining work

- No known remaining work.

## Final commit and tag

- Final commits and `worksheet/confidence-policy-no-critical-fields` tag created at wrap-up.
