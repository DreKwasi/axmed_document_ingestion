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
- 2026-09-07: User confirmed pure Tailwind CSS utility usage with zero bespoke CSS bloat.
- 2026-09-07: Built modular Vue 3 components:
  - `frontend/src/components/SourceTable.vue`: Clean table of all uploaded sources with status, products count, overall extraction confidence, filename, format badge, and download links.
  - `frontend/src/components/SourceDetailHeader.vue`: Source overview, schema & commercial terms metadata strip, inline status & confidence metadata, and clear, distinct action buttons (outline "Open original ↗" and solid emerald CTA "✓ Review source").
  - `frontend/src/components/ProductTable.vue`: Table of extracted products with trade name, active ingredients (INN), dosage form & route, quoted quantity, quoted price, row-level extraction confidence badges, and review issue flags.
  - `frontend/src/components/ProductDetailDrawer.vue`: Slide-over inspector displaying all remaining columns for the product (identity, packaging, pricing & commercial terms, quantity & supply, regulatory & compliance, field evidence & provenance) with in-place editable fields and zero inline approve/reject buttons.
  - `frontend/src/components/ReviewModal.vue`: Dedicated dialog for overall source review decision (approve/reject) with optional review note and validation issue guards.
- 2026-09-07: Refactored `frontend/src/App.vue` to orchestrate views, live SSE events, and state. Fixed drawer auto-open so it only opens when clicking a product row.
- 2026-09-07: Added Google Fonts Inter typography to `frontend/index.html`.
- 2026-09-07: Updated `frontend/src/App.spec.ts` with 10 comprehensive unit tests covering source list, product breakdown, row confidence, product details drawer, in-place corrections, and the review decision modal.
- 2026-09-07: Updated `frontend/e2e/review.spec.ts` to exercise confirming mapping, row-click drawer inspection, saving correction, closing drawer, opening review modal, and approving the source.

## Tests, app run, and validation

- `npm --prefix frontend run lint`: 0 errors, 0 warnings.
- `npm --prefix frontend test`: 10 passed in `App.spec.ts`.
- `npm --prefix frontend run build`: production bundle built cleanly in <400ms (`vue-tsc` + `vite build`).
- `npm --prefix frontend run test:e2e`: Playwright E2E passed (both `batch.spec.ts` and `review.spec.ts` 2/2 passed).
- `bin/agent-validate targeted`: all frontend checks (lint, vitest), backend checks (Ruff, mypy 33 files, pytest 78 tests) passed.

## Review findings and resolutions

- User review: Fixed auto-opening of product drawer upon opening a source; drawer now opens exclusively on clicking a product row.
- User review: Fixed visual confusion between badges and buttons in `SourceDetailHeader.vue` by moving status & confidence to clean inline text with status dots under the title, and providing clear, high-contrast action buttons on the right.
- User review: Removed the static multi-event extraction activity card (which displayed completed checklists 1, 2, 3 all at once). Replaced with a single dynamic in-progress banner that displays only the active extraction phase/message while extraction is ongoing and automatically dismisses once extraction completes.

## Docs updated

- `docs/system/test-catalog.md`
- `docs/worksheets/frontend-overhaul.md`

## Handoff / remaining work

- Work complete and verified against automated unit and E2E suites.

## Final commit and tag

- Worksheet: `worksheet/frontend-overhaul`.
