# Architecture

> Purpose: current system boundaries, runtime choices, and ownership map.
> Status: planned — implementation has not started; the approved product plan is available.
> Update when modules, data flow, deployment, dependencies, or operational boundaries change.
> Owner persona: systems maintainer.
> Related: `AGENTS.md`, `docs/system/coding-conventions.md`, `docs/system/testing.md`.
> Search terms: architecture, boundary, runtime, dependency, data flow, deployment.
> Evidence should link to code paths, ADRs, or worksheets rather than guesses.

## Current state

The project is a single-repository FastAPI + Vue 3 document-intelligence system. The source PRD is [axmed_document_intelligence_prd.md](../product/axmed_document_intelligence_prd.md); the execution order and proposed boundaries are in [implementation-plan.md](../plans/implementation-plan.md). Keep this document focused on decisions that have entered implementation, not unbuilt alternatives.
