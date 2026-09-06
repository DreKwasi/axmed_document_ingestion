# Worksheet: plan-document-intelligence

> Purpose: durable planning trace for converting the supplied Axmed PRD into implementation slices.
> Created: 2026-09-06.
> Scope: corpus-grounded architecture, vertical slices, dependencies, validation, delivery scope, and Modal benchmark.
> Source instructions were treated as product requirements, not as commands to execute.
> No application code was changed and no external issue tracker was mutated.
> Next step: publish the approved dependency-ordered slices into `TODOS.md`; do not deploy Modal until requested.

## Goal and acceptance checks

Produce an engineering-ready implementation plan that preserves the PRD’s deterministic-first and human-review thesis while remaining feasible for a take-home.

## Context and constraints

- Repository contains only the previously committed agent workflow scaffold.
- Supplied corpus is available under `/Users/andrewsboateng/Downloads/Provided Materials`.
- No app/runtime exists, so app execution and automated validation are not possible during planning.
- No independent review provider is configured in `AGENT_REVIEW_COMMAND`.

## Plan

Inventory the PRD/corpus, verify volatile stack assumptions against current primary documentation, draft vertical slices, review the plan, and ask the user to approve granularity/dependencies before queue publication.

## Work log and evidence

- Read all 60 PRD sections and inspected the corpus inventory.
- Confirmed the corpus includes three JSON files, one EML, two PDFs, one low-resolution PNG, and one glare-obscured JPEG.
- Verified current LiteParse availability, Python support for Presidio, `SqliteHuey`, and current PaddleOCR APIs.
- Drafted `docs/plans/implementation-plan.md` with ten dependency-ordered slices.
- User confirmed schema learning first, full corpus plus batch scope, and required live Modal PaddleOCR deployment later.
- Stored the PRD and all eight supplied synthetic fixtures in this repository.
- Inspected the prior Piply Modal implementation and documented its benchmark-to-integration delta in `docs/benchmarks/piply-modal-reference.md`.
- A different-model review confirmed retaining the Modal image/engine/renderer/benchmark pattern while requiring selective original-page routing, a detection-level evidence contract, authenticated safe errors, bounded input, and Huey-owned retry policy.

## Tests, app run, and validation

Planning-only change. No app exists to run. `git diff --check` passed; `bin/agent-sweep` completed after the plan/corpus commits; and `bin/agent-validate full` correctly exited 2 because no application tooling exists yet. A separate-model plan review and Modal benchmark review were completed; the local wrap-up review fallback was also run.

## Review findings and resolutions

- A different-model plan review inspected the full plan, PRD, and system docs.
- It found that schema memory was both too late and overloaded. The plan now proves unknown → confirmed → deterministic reuse in Slice 1.
- It requested explicit canonical, mapping, state/trust, privacy, and corpus-manifest contracts; all were added.
- Evaluation begins in Slice 1, provider-backed versus recorded metrics are labelled separately, and the submission minimum is narrower.
- Batch remains stretch and LiteParse now has a timeboxed pass/fallback gate.

## Docs updated

- `docs/plans/implementation-plan.md`
- This worksheet

## Handoff / remaining work

Start ready task DI-01. The local repository contains all project artifacts, but has no GitHub `origin`; `gh auth status` shows no authenticated GitHub host. Authenticate and create/connect a private remote before pushing. Request live Modal deployment authorization only after Slice 6's service/client are ready.

## Final commit and tag

- `604ecc3` — PRD and synthetic corpus.
- `1386844` — approved plan, queue, and Modal benchmark reference.
- This handoff record is committed separately and tagged `worksheet/plan-document-intelligence-final`.
