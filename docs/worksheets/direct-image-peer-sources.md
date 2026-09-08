# Worksheet: direct-image-peer-sources

> Purpose: replace the intermediate image comparison card with immediate peer source results in the table and direct candidate review.
> Related: `docs/plans/implementation-plan.md`, `docs/system/architecture.md`, `docs/worksheets/image-attempt-confidence.md`.
> Git: uncommitted changes preserved; keep checks targeted and clean.

## Goal and acceptance checks

- For image/OCR sources, immediately expose OCR-assisted and Direct vision as two peer sources on Home.
- Do not auto-redirect single image uploads into an intermediate comparison screen.
- Remove the legacy "Compare image extractions" interstitial card from `App.vue`.
- Clicking either the OCR-assisted or Direct vision source from Home opens that candidate's product breakdown and review state directly.
- Allow seamless switching between peer readings in the detail view.
- All frontend and backend tests pass.

## Context and constraints

- Architecture and implementation plan specify: "For an uploaded image, the OCR-assisted and direct-vision readings are exposed as two source results; because both read the same physical source, they share its source-condition confidence."
- The user highlighted the unintended appearance of the "Compare image extractions" screen with "Review this extraction" buttons.

## Plan

1. Update `SourceTable.vue` so image documents consistently produce two peer source rows (`OCR-assisted` and `Direct vision`), both while in progress and once completed.
2. Update `App.vue` to:
   - Stay on Home upon image upload instead of forcing an unselected detail view.
   - Remove the `<section v-else-if="selectedDocument.image_extraction_attempts?.length">` ("Compare image extractions") interstitial card.
   - Direct-select and activate the clicked attempt approach when opening an image source row.
   - Automatically activate the selected candidate so `ProductTable` and detail drawer render directly.
3. Update `SourceDetailHeader.vue` to remove the "Compare extraction results" status label and provide approach switching between the peer readings.
4. Add component tests in `frontend/src/App.spec.ts`.
5. Validate via `bin/agent-validate targeted` and record feedback.
## Work log and evidence

- 2026-09-08: Updated `SourceTable.vue` so image documents consistently produce two peer source rows (`OCR-assisted` and `Direct vision`), both when processing and when complete.
- 2026-09-08: Updated `App.vue` to avoid auto-redirecting single image uploads away from the sources table.
- 2026-09-08: Removed the `<section v-else-if="selectedDocument.image_extraction_attempts?.length">` ("Compare image extractions") interstitial card from `App.vue`.
- 2026-09-08: Enhanced `openDocument` and `openCandidateForReview` in `App.vue` to directly load the selected peer extraction so the quotation, product table, and detail drawer render immediately.
- 2026-09-08: Added a peer reading switcher in `SourceDetailHeader.vue` allowing instantaneous toggling between OCR-assisted and Direct vision readings with matching source titles.

## Tests, app run, and validation

- Added regressions in `frontend/src/App.spec.ts`:
  - `opens the selected image approach directly without a comparison interstitial`
  - `stays on the Home page when an image is uploaded`
  - `allows switching between OCR-assisted and Direct vision readings in detail header`
- `npm --prefix frontend test`: 21 tests passed across 2 test files.
- `npm --prefix frontend run lint`: clean, 0 errors, 0 warnings.
- `npm --prefix frontend run build`: Vite build succeeded.
- `bin/agent-validate targeted`: all frontend (ESLint + Vitest) and backend (Ruff + Mypy + 92 Pytest) checks passed.

## Review findings and resolutions

- Verified that neither candidate is favored automatically: both are listed as peers on Home, each with its own extraction and mapping confidence.
- Verified that opening an approach populates the canonical quotation and line items table without intermediate interstitial screens.

## Docs updated

- Updated `docs/system/test-catalog.md` and `docs/worksheets/direct-image-peer-sources.md`.
- Added operational feedback to `docs/agent-feedback.md`.

## Handoff / remaining work

- None. Both peer readings render directly upon selection and as two sources in the table.

## Final commit and tag

- Uncommitted workspace changes preserved as per environment instructions.
