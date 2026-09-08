# Worksheet: source-header-layout-cleanup

> Purpose: durable handoff trace for one coherent change.
> Create this file before meaningful implementation and commit it with the change.
> Record evidence, decisions, commands, results, review, and unfinished work—not private chain-of-thought.
> Another agent should be able to resume from this document alone plus the code.
> Finalize with the associated commit and `worksheet/<name>` tag when Git is available.
> Keep entries concise, factual, and timestamped where useful.

## Goal and acceptance checks

- Eliminate redundant "pdf" / "PDF" appearances in `SourceDetailHeader.vue`.
- Remove the redundant "Source Schema / System" metadata card completely.
- Display page counts (and external ERP systems when applicable) directly in the metadata line next to the filename.
- Restructure the metadata card grid to a balanced 4-column layout (`grid-cols-2 md:grid-cols-4`).

## Context and constraints

- Uploaded PDFs showed a format badge `PDF` next to the filename and simultaneously rendered a card labeled `SOURCE SCHEMA / SYSTEM` containing `pdf · 2 pages`.
- The user requested removing the source system card completely and displaying page count in the metadata line next to the filename and format badge.
- Structured ERP/JSON imports should still present their system name/version without requiring a dedicated card.

## Plan

1. In `SourceDetailHeader.vue`, add an `externalSystem` computed helper to extract non-generic system names (e.g. `SupplierERP v1`).
2. Move page count and external system info into the subtitle metadata line beside `filename` and `formatBadge`.
3. Remove the `Source Schema / System` card and change the metadata grid to `grid-cols-2 md:grid-cols-4`.
4. Update unit tests in `frontend/src/App.spec.ts` and document in `docs/system/test-catalog.md`.
5. Run full validation (`bin/agent-validate targeted`).

## Work log and evidence

- Modified `SourceDetailHeader.vue` to introduce `externalSystem` and render page count / external systems in the metadata line.
- Removed the 5th metadata card, leaving the 4 core quotation cards: Supplier, Delivery Terms, Document Type / Ref, Against RFQ.
- Added test coverage in `App.spec.ts` for PDF page count in metadata line and absence of redundant source schema card.
- Fixed ESLint newline warning on opening grid `<div>`.

## Tests, app run, and validation

- `npm --prefix frontend test`: 18 passing tests in 2 test suites.
- `npm --prefix frontend run lint`: 0 warnings, 0 errors.
- `npm --prefix frontend run build`: cleanly bundled.
- `bin/agent-validate targeted`: all frontend lint/tests, backend ruff, backend mypy, and 92 pytest cases passing.

## Docs updated

- `docs/system/test-catalog.md`: cataloged test coverage for `SourceDetailHeader` metadata line and card layout.

## Handoff / remaining work

- No remaining items. Header is clean, balanced, and non-redundant.

## Final commit and tag
