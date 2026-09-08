# Worksheet: backend-csv-export

> Purpose: make the backend database projection the single source of truth for flattened CSV exports.

## Goal and acceptance checks

- Add a downloadable backend CSV endpoint backed by persisted document and extraction-attempt records.
- Flatten one row per product and one summary row for terminal productless results.
- Export OCR-assisted and Direct vision image attempts as distinct source results matching the Home table.
- Exclude active processing records.
- Make the frontend initiate the backend download without rebuilding CSV data locally.
- Preserve the approved user-facing column contract and confidence/issue/review context.

## Context and constraints

- The frontend Home projection expands one image document into peer extraction results, while the prior browser serializer iterated only parent documents.
- Source-level values repeat on product rows by design; the `source` column identifies which document or image attempt each product belongs to.

## Plan

- Add a failing endpoint test using persisted peer image-attempt records.
- Implement a backend flattening module and CSV response route.
- Replace the frontend serializer with a backend download URL.
- Run focused API, frontend, and browser-download checks; update system docs and complete staged review.

## Work log and evidence

- Added `GET /api/v1/documents/export.csv` and a backend flattener over serialized persisted records.
- Projected completed/failed image attempts independently using their stored result, confidence, and failure state.
- Removed the duplicate frontend CSV serializer; the Export CSV action now downloads the backend response.
- Preserved source-level repetition per product row, which is required for a flat table, while adding the source-result label that distinguishes peer image attempts.

## Tests, app run, and validation

- Red: endpoint request initially resolved as a document ID and returned 404.
- Green: ordinary persisted quotation exports as its product rows.
- Red: an image parent initially exported as one row and lost its two peer attempt results.
- Green: OCR-assisted and Direct vision attempts export as separate rows with their own products and confidence.
- Red/green: frontend component test first observed the obsolete Blob serializer, then passed against the backend URL.
- `bin/agent-validate targeted`: 24 frontend tests and 97 backend tests passed; lint, Ruff, and mypy passed.
- Focused Playwright download journey: 1 passed against the running API and frontend.
- `bin/agent-validate full`: production build, 24 component tests, 5 Playwright journeys, 98 backend tests, and 5 evaluation tests passed; recorded evaluation run completed.

## Review findings and resolutions

- Research/plan/implementation review dispatch found no configured independent provider, so isolated systems, quality, code-quality, security, performance, and UX passes were completed locally.
- Systems: one backend route now owns the projection; the dynamic document route remains after the static export route.
- Quality: regression coverage distinguishes ordinary documents from image peers and verifies the browser download seam.
- Security/performance: the endpoint exposes only the established serialized user-facing document model, excludes active records, and performs one ordered document query; no raw upload or provider payload is returned.
- UX: the filename remains `axmed-export.csv`, while source labels now correspond to the rows shown on Home.
- Final two-axis review found that document reviews could be repeated on both peer image rows; attempt projections now omit those ambiguous reviews. Added coverage for a failed productless attempt and exclusion of an active sibling attempt.
- Review observations about persisted confidence recomputation and typed projection models are broader persistence-model improvements: the current API serializer already derives those public values from stored extraction evidence, and changing that storage contract is outside this flattening fix.

## Docs updated

- Architecture and deep-dive ownership notes.
- Backend and frontend README export descriptions.
- Test catalog and implementation plan.
- Agent feedback on projection ownership.

## Handoff / remaining work

- No known functional remainder. The existing Starlette/AnyIO deprecation warning is unrelated.

## Final commit and tag

- Associated commits are tagged `worksheet/backend-csv-export`.
