# Architecture

> Purpose: current system boundaries, runtime choices, and ownership map.
> Status: Slice 1 implemented — FastAPI/Vue/SQLite document intake, mapping memory, and evaluation persistence are running locally.
> Update when modules, data flow, deployment, dependencies, or operational boundaries change.
> Owner persona: systems maintainer.
> Related: `AGENTS.md`, `docs/system/coding-conventions.md`, `docs/system/testing.md`.
> Search terms: architecture, boundary, runtime, dependency, data flow, deployment.
> Evidence should link to code paths, ADRs, or worksheets rather than guesses.

## Current state

The project is a single-repository FastAPI + Vue 3 document-intelligence system. The source PRD is [axmed_document_intelligence_prd.md](../product/axmed_document_intelligence_prd.md); the execution order is in [implementation-plan.md](../plans/implementation-plan.md). Slice 1 applies checked-in Alembic migrations and persists documents, quotations, fingerprinted mappings, and evaluation runs in `data/app.db`. A recorded mapping provider is an explicit development/evaluation adapter; the mapping lookup in `backend/app/services.py` prevents trusted cache hits from invoking it and scopes reuse by source system, declared source version, and normalized fingerprint. Keep this document focused on decisions that have entered implementation, not unbuilt alternatives.
