# Architecture

> Purpose: current system boundaries, runtime choices, and ownership map.
> Status: Slices 1–2 implemented — FastAPI/Vue/SQLite JSON intake, commercial review, source retention, and queued learning feedback run locally.
> Update when modules, data flow, deployment, dependencies, or operational boundaries change.
> Owner persona: systems maintainer.
> Related: `AGENTS.md`, `docs/system/coding-conventions.md`, `docs/system/testing.md`.
> Search terms: architecture, boundary, runtime, dependency, data flow, deployment.
> Evidence should link to code paths, ADRs, or worksheets rather than guesses.

## Current state

The project is a single-repository FastAPI + Vue 3 document-intelligence system. The source PRD is [axmed_document_intelligence_prd.md](../product/axmed_document_intelligence_prd.md); the execution order is in [implementation-plan.md](../plans/implementation-plan.md). Checked-in Alembic migrations persist documents, quotations, source files under a generated local name, fingerprinted mappings, review commands, correction evidence, queued review-learning jobs, and evaluation runs in `data/app.db`. A legacy local Slice 1 database is baselined only when its table set exactly matches the known pre-Alembic schema. A recorded mapping provider is an explicit development/evaluation adapter; the mapping lookup in `backend/app/services.py` prevents trusted cache hits from invoking it and scopes reuse by source system, declared source version, and normalized fingerprint. Commercial validation has one public seam, `validate_and_derive`; supplier aliases remain exclusively in schema mapping. The review footer remains inside each document table so review status, corrections, and decisions stay together. A correction creates a human-evidence/audit revision and a safe learning job containing the field interpretation—not a copied historical price. Slice 3 owns PII-safe asynchronous model execution of that job. Keep this document focused on decisions that have entered implementation, not unbuilt alternatives.
