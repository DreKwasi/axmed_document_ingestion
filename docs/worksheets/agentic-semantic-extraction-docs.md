# Worksheet: agentic-semantic-extraction-docs

> Purpose: reconcile schema-reuse documentation with the current implementation and define a bounded semantic-extraction investigation loop.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> This documentation worksheet was superseded by `di-17-langchain-semantic-agent.md`; the user requested no automatic commits or tags.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Remove claims that reviewed or repeated schemas currently bypass semantic model extraction.
- Describe the current per-document, source-grounded JSON behavior accurately.
- Document a proposed bounded investigation loop for semantic extraction without assigning deterministic routing or human authority to the model.
- Clarify the synchronous request boundary and background processing boundary.

## Context and constraints

- Migration `20260907_19` retired reusable JSON mappings and schema fingerprints.
- Recorded JSON responses are exact-content offline fixtures, not learned mappings.
- Do not introduce product behavior changes in this documentation-only session.

## Plan

1. Audit user-facing and system documentation for stale reuse claims.
2. Update architecture, PRD, README, and write-up language consistently.
3. Run repository reviews and documentation/full validation.

## Work log and evidence

- 2026-09-09: Confirmed `_extract_json_document` processes each JSON independently and the current migration drops reusable mapping state.
- 2026-09-09: Replaced stale schema-reuse, Huey, batch-table, and zero-model-path claims in the current README/write-up narrative.
- 2026-09-09: Added PRD §32.1 and an architecture section that distinguish the planned bounded investigation loop from current fixed semantic calls.
- 2026-09-09: Queued implementation as DI-17 rather than presenting the design as delivered behavior.

## Tests, app run, and validation

- `bin/agent-validate targeted` passed: frontend lint, 31 Vitest tests, Ruff, mypy, and 101 backend tests.
- `API_PORT=8011 WEB_PORT=5181 bin/dev` started the FastAPI and Vite applications; `GET /health` returned the expected healthy service payload and the frontend root returned HTTP 200.
- `bin/agent-validate full` reached the frontend production build and failed on an existing TypeScript fixture mismatch at `frontend/src/App.spec.ts:110` (`"rejected"` assigned to a literal `"pending_review"` type). This session did not modify that test or application type and did not broaden the documentation task to repair it.

## Review findings and resolutions

- Research review: no independent provider configured. Systems pass found contradictory historical/current documentation; security-domain pass retained deterministic media gates, image privacy boundary, and human authority; quality pass required explicit “planned” labeling and exact-fixture language.
- Plan review: no independent provider configured. The change is documentation-only and reversible; implementation is separately queued with test and evaluation requirements.
- Implementation review: two isolated review passes found residual PRD schema-reuse language, an inaccurate CSV-record description, missing planned coverage, and an incomplete worksheet. The PRD and architecture wording were corrected, planned orchestration coverage was added to `docs/system/testing.md`, and wrap-up evidence was recorded here.
- Wrap-up review: no independent provider was configured. The final persona pass verified current-versus-planned labels, deterministic ownership boundaries, user-requested terminology exclusions, validation evidence, and the DI-17 handoff. `bin/agent-sweep` completed over `HEAD~10..HEAD`; no additional issue was introduced by this documentation change.

## Docs updated

- `README.md`
- `WRITEUP.md`
- `backend/README.md`
- `TODOS.md`
- `docs/product/axmed_document_intelligence_prd.md`
- `docs/system/architecture.md`
- `docs/system/evaluations.md`
- `docs/plans/implementation-plan.md`
- `docs/agent-feedback.md`

## Handoff / remaining work

- DI-17 is ready for implementation. It must preserve the current per-document evidence model while moving JSON semantic work behind the persisted background-task boundary.
- Full validation remains blocked by the pre-existing `frontend/src/App.spec.ts:110` TypeScript fixture mismatch; targeted validation is clean.

## Final commit and tag

- None. These changes remain uncommitted at the user's request.
