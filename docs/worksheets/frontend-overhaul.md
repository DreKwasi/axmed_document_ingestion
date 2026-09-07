# Worksheet: frontend-overhaul

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Redesign the frontend to be clean, elegant, and focused, removing cluttered and unnecessary UI cards.
- Home page displays a clean, comprehensive table of all uploaded sources with extraction confidence, product counts, status, and download links.
- Opening a source displays the source schema and extraction metadata, overall confidence, and a table of extracted products with per-row extraction confidence.
- Clicking any product row opens an inspector/drawer with all remaining columns that make up that product.
- Field values are editable directly by the user to save review corrections; remove all per-row approve/reject buttons.
- Overall approve/reject is triggered via a dedicated "Review" button that opens a modal dialog allowing optional reviewer notes.
- Pass all unit tests, linters, and Playwright E2E tests.

## Context and constraints

- Respect existing backend APIs and contracts (`/api/v1/documents`, `/reviews/approve`, `/reviews/reject`, `/reviews/correct`, `/events/stream`).
- Do not modify unrelated backend changes in the working tree.
- Keep Tailwind CSS utility styling clean and responsive.

## Plan

1. Create modular Vue components under `frontend/src/components/` (`SourceTable.vue`, `SourceDetailHeader.vue`, `ProductTable.vue`, `ProductDetailDrawer.vue`, `ReviewModal.vue`, `MappingConfirmBanner.vue`).
2. Refactor `frontend/src/App.vue` to orchestrate views, live SSE events, and data fetching.
3. Update `frontend/index.html` with modern Inter typography.
4. Update `frontend/src/App.spec.ts` and ensure Playwright E2E tests (`frontend/e2e/`) align.
5. Run `bin/agent-validate targeted`, browser subagent verification, and `bin/agent-validate full`.

## Work log and evidence

- 2026-09-07: Researched requirements from user voice note and existing frontend codebase. Baseline tests passed (`bin/agent-validate targeted`: 8 frontend tests, 78 backend tests). Created implementation plan.

## Tests, app run, and validation

- Pending execution approval.

## Review findings and resolutions

- Research/plan review: Verified compatibility of `_apply_field_patch` and `reviewDocument` for flexible field editing and review modal approval/rejection.

## Docs updated

- Pending completion.

## Handoff / remaining work

- Awaiting user approval of implementation plan before executing code changes.

## Final commit and tag

- Pending completion.
