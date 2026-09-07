# Worksheet: review-policy-v6

> Purpose: durable handoff trace for PRD v6 confidence and human-review policy.
> Status: complete.
> Owner: backend/frontend delivery.

## Goal and acceptance checks

- Persist independent system decision and human outcome states.
- Replace user-facing confidence percentages with key-field coverage and categorical reliability.
- Auto-accept only records meeting complete critical-field, reliability, validation, and conflict requirements.
- Keep the review queue exception-based; approvals are optional-note, corrections audit values, and rejections require a structured reason.

## Context and constraints

PRD v6 supersedes the prior confidence section. Existing frontend redesign work is uncommitted; this slice must integrate through its public types/components without discarding it. Existing unrelated backend changes remain unstaged.

## Plan

1. Replace the local PRD confidence/review policy and record the vocabulary.
2. Add relational decision/reliability/rejection-reason persistence and migration.
3. Implement deterministic coverage/reliability/system-routing policy at quotation persistence.
4. Update review commands and API serialization; add targeted backend tests.
5. Update UI types and review/summary components through narrow integration points.
6. Validate, run the app, review, document, commit, and tag.

## Work log and evidence

- 2026-09-07: Compared PRD v5/v6; v6 replaces the confidence model with coverage, field reliability, and separate review decision semantics.
- 2026-09-07: Added the v6 policy and ubiquitous language to local product documentation.
- 2026-09-07: Added migration `20260907_15`, observable field-reliability routing, system-decision persistence, structured rejections, and the exception-only review queue.
- 2026-09-07: Replaced Home/detail/product numeric confidence display with critical-field coverage and persisted reliability categories; the review modal now selects a structured rejection reason.

## Tests, app run, and validation

- Targeted backend: `22 passed` (`test_confidence`, `test_commercial_review`, `test_migrations`).
- Full validation: frontend lint/Vitest/build, 2 Playwright journeys, backend Ruff/mypy, 81 backend tests, and 5 evaluation tests all passed.
- Live-browser check: Home presents the recovered image source as `3 of 6 critical fields`, `Review`, and no user-facing confidence percentage.

## Review findings and resolutions

- Research and plan reviews found no independent provider configured; local systems, domain, quality, and compatibility review completed instead.

## Docs updated

- `docs/product/axmed_document_intelligence_prd.md`
- `CONTEXT.md`
- `docs/system/architecture.md`
- `docs/system/test-catalog.md`
- `docs/plans/implementation-plan.md`

## Handoff / remaining work

None.

## Final commit and tag

`af28694`, `9769bba`, `471b6ad`, `e851beb`, `ebb806b`, `ac25507`, `412dc92`, `b4094db`; worksheet tag `worksheet/review-policy-v6`.
