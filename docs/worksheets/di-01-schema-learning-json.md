# Worksheet: DI-01 schema-learning JSON

> Purpose: durable handoff trace for the first runnable product vertical slice.
> Scope: FastAPI, Vue, SQLite, safe JSON intake, recorded mapping proposal, confirmation, and trusted mapping reuse.
> Status: implementation complete; final validation and commit tag pending.
> The PRD is stored at `docs/product/axmed_document_intelligence_prd.md`; the approved delivery sequence is `docs/plans/implementation-plan.md`.
> No live LLM, OCR service, Modal resource, or external deployment is used in this slice.
> Recorded mapping telemetry is explicitly labelled simulated/recorded and is not a claim of live provider cost or latency.
> Runtime data is local-only under ignored `data/`.

## Goal and acceptance checks

- Accept a safe JSON supplier export and persist its source receipt plus canonical quotation in SQLite.
- For an unknown fingerprint, use only a versioned recorded mapping response and require human confirmation.
- For an identical confirmed shape with different values, deterministically reuse the trusted mapping with zero semantic calls.
- Fail an unsupported changed shape safely; do not silently reuse a prior mapping.
- Persist and display a Level-1 recorded evaluation with canonical fidelity, mapping efficiency, and safety/uncertainty rubrics.

## Context and constraints

- One repository contains the whole project.
- The canonical contract preserves quotation, supplier, commercial, product, packaging, quantity, pricing, supply, regulatory, and evidence fields with explicit nullable values.
- The local recorded provider is a test/development adapter, not production semantic extraction. A live adapter remains a later tracked task.
- `piply-modal` was assessed only as a future provider benchmark; no Modal deployment is authorized in this slice.

## Plan

1. Establish a dependency-managed FastAPI and Vue application with SQLite models.
2. Store a normalized structural fingerprint and an explicit declarative mapping fixture for the supplied Sanova JSON export.
3. Create upload, mapping confirmation, and evaluation APIs plus a review/evaluation UI.
4. Test cold, confirm, warm, drift, invalid-media, repeat-receipt, evaluation, and UI confirmation paths.
5. Run the app locally, inspect the rendered UI, obtain independent implementation review, then run full validation and commit.

## Work log and evidence

- 2026-09-06: Implemented FastAPI factory/lifespan, local SQLite tables, canonical Pydantic model, safe JSON validation, secure generated storage names, and recorded semantic mapping adapter.
- 2026-09-06: Implemented explicit mapping confirmation. Confirmed mappings are keyed by source system and normalized schema fingerprint; a warm schema is handled deterministically.
- 2026-09-06: Added the Vue review desk and SQLite-backed evaluation lab. The UI displays mapping calls and recorded cold token/cost telemetry.
- 2026-09-06: Browser integration exposed two defects: the frontend default API origin did not match the supervised bind address, and duplicate source receipts used deterministic IDs. Changed the default to `127.0.0.1` and generated an independent UUID receipt for each submission while retaining content hashing.

## Tests, app run, and validation

- `make dev` started API at `127.0.0.1:8000` and Vue at `127.0.0.1:5173`; `/health` returned `{"status":"ok","service":"axmed-document-intelligence"}`.
- Browser review test uploaded the supplied Sanova export, rendered all three line items with source evidence, and reported a trusted warm path with zero semantic calls.
- Browser evaluation test triggered a real persisted SQLite run: 1/1 passed, fidelity 100%, warm calls 0, recorded cost `$0.00214`.
- Browser visual review confirmed the review desk layout and readable quotation table at the normal desktop viewport.
- `make lint`, `make test`, `make build`, and `bin/agent-validate full` passed after the final fixes: 10 backend tests and 2 frontend tests. FastAPI's current TestClient dependency emits two upstream deprecation warnings only.

## Review findings and resolutions

- Independent cross-model implementation review found five P1 gaps: self-reported warm evaluation, schema-version-insensitive reuse, malformed mapped-value 500s, missing conflict state, and missing migrations. The slice now measures an actual cold/warm mapping contract, keys mappings by source system/version/fingerprint, tracks mapping failures as failed receipts, presents changed schemas for human resolution, and runs checked-in Alembic migrations.
- The reviewer also noted null/uncertainty was untested. Required mapped source values now remain `null` and create structured review issues; the direct unit test protects this behavior.
- Local browser test exposed origin and duplicate-receipt defects; both were fixed with regression coverage.

## Docs updated

- `AGENTS.md`, `docs/system/architecture.md`, `docs/system/testing.md`, `docs/system/test-catalog.md`, and `docs/system/evaluations.md` describe the new system and its checks.
- `README.md` documents a fresh local install/start/validation path.

## Handoff / remaining work

- Resolve any independent-review findings, update this worksheet and the task queue, then commit/tag DI-01.
- DI-02 is next: deterministic commercial rules, provenance-visible review decisions, correction revisions, approvals, and rejection.

## Final commit and tag

`d5c1796` — `feat: add schema-learning document intake slice`  
`worksheet/di-01-schema-learning-json`
