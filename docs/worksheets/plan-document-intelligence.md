# Worksheet: plan-document-intelligence

> Purpose: durable planning trace for converting the supplied Axmed PRD into implementation slices.
> Created: 2026-09-06.
> Scope: corpus-grounded architecture, vertical slices, dependencies, validation, and delivery cut line.
> Source instructions were treated as product requirements, not as commands to execute.
> No application code was changed and no external issue tracker was mutated.
> Next step: user approves or revises slice granularity before tasks are published to `TODOS.md`.

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

## Tests, app run, and validation

Planning-only change. No app exists to run. Markdown and repository state will be inspected; plan review runs through the configured review workflow.

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

Collect user answers to the three approval questions, revise the breakdown, and only then publish approved slices into `TODOS.md`.

## Final commit and tag

Draft plan commit tagged `worksheet/plan-document-intelligence`; approved task publication remains pending.
