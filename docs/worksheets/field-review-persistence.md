# Worksheet: field-review-persistence

> Durable implementation trace for one coherent change; keep entries factual and concise.

## Goal and acceptance checks

- Persist every non-null extracted leaf value independently of the JSON snapshot.
- Store confidence, extraction provenance, and a human-review status for each value.
- Transition field statuses on correction, approval, and rejection.
- Backfill existing quotations through Alembic and expose the records through the API.

## Work log and evidence

- Added `quotation_field_values`, keyed by quotation and canonical field path, with `value_json`, `confidence`, `review_status`, extraction method, and source location.
- Extraction and correction flows replace the field-value projection; human corrections are marked `corrected`, approvals/rejections update all field rows.
- Migration `20260906_14` backfilled the workspace; the database now contains 1,543 field-value rows at revision `20260906_14`.
- The API exposes the projection as `quotation.field_reviews`; the JSON quotation remains the immutable snapshot.

## Validation

- `pytest backend/tests/test_migrations.py backend/tests/test_commercial_review.py -q`: 16 passed.
- `bin/agent-validate full`: frontend lint/test/build/e2e passed; Ruff, mypy, 75 backend tests, and recorded evaluation command passed. Recorded evaluation summary: 1 passed, 5 not run.

## Review

- The value table intentionally stores non-null extracted leaves only; absent values remain explicit nulls in the snapshot and are not assigned fabricated confidence.
- Fields without matching provenance are stored with confidence `0.00` and extraction method `unattributed`, making them visible as review-required uncertainty.
- Independent review provider was unavailable; isolated implementation review checked lifecycle coverage, FK-safe projection replacement, migration backfill, and the reported evaluation skips.

## Handoff

- Update the test catalog and architecture docs with migration `20260906_14`.
- Commit this worksheet with the implementation; pre-existing user-owned worktree changes remain unstaged.
